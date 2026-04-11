"""Point d'entrée principal de l'agent de veille technologique.

Orchestration complète du pipeline :
    collecte → déduplication → filtrage → extraction → analyse → briefing

Usage::

    # Exécution directe
    python -m veille_agent

    # Via le script installé (pyproject.toml)
    veille_agent

    # Dry-run (sans appel Claude ni écriture SQLite)
    python -m veille_agent --dry-run

    # Avec envoi par email
    python -m veille_agent --email vous@gmail.com
"""

import argparse
import importlib.resources
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from veille_agent.bin.analyst import ScoredItem, analyze_batch
from veille_agent.bin.briefing import (
    generate_html_briefing,
    generate_markdown_briefing,
)
from veille_agent.bin.collector import (
    collect_arxiv,
    collect_github_trending,
    collect_rss,
    deduplicate,
    mark_seen,
)
from veille_agent.bin.config import WatchConfig
from veille_agent.bin.filter import pre_filter
from veille_agent.bin.mailer import send_email
from veille_agent.bin.profile import UserProfile, load_profile
from veille_agent.bin.reader import fetch_fulltext

load_dotenv()


def _get_package_dir(folder_name: str) -> Path:
    """Retourne le chemin absolu d'un sous-dossier du package.

    Args:
        folder_name: Nom du sous-dossier (``config``, ``data``, ``log``).

    Returns:
        Chemin vers le dossier.

    Raises:
        NameError: Si le dossier n'existe pas dans le package.
    """
    try:
        with importlib.resources.path(f"veille_agent.{folder_name}", "") as p:
            return Path(p)
    except (NameError, ModuleNotFoundError) as exc:
        logging.error("Le dossier %s n'existe pas.", folder_name, exc_info=True)
        raise NameError(f"Dossier introuvable : {folder_name}") from exc


def _setup_logging(log_path: Path) -> None:
    """Configure le logger applicatif."""
    log_file = log_path / "app.log"
    logging.basicConfig(
        filename=str(log_file),
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.DEBUG,
    )


def run(
    config: WatchConfig,
    profile: UserProfile,
    db_path: str,
    output_dir: Path,
    email_to: str | None = None,
    dry_run: bool = False,
) -> list[ScoredItem]:
    """Exécute le pipeline complet de veille.

    Args:
        config: Paramètres techniques de l'agent (sources, batch size…).
        profile: Profil utilisateur chargé depuis ``profile.yaml``.
        db_path: Chemin vers la base SQLite de déduplication.
        output_dir: Dossier de sortie pour les briefings.
        email_to: Si fourni, envoie le briefing HTML à cette adresse.
        dry_run: Si ``True``, collecte et filtre sans appeler Claude ni SQLite.

    Returns:
        Liste des :class:`~veille_agent.bin.analyst.ScoredItem` produits.
    """
    print("1/5 — Collecte des sources...")
    items = []
    items += collect_rss(config.rss_feeds, since_days=config.rss_since_days)
    items += collect_arxiv(config.arxiv_categories)
    items += collect_github_trending(config.github_topics)
    print(f"    {len(items)} items bruts collectés")

    if not dry_run:
        print("2/5 — Déduplication...")
        items = deduplicate(items, db_path=db_path)
        print(f"    {len(items)} nouveaux items")
    else:
        print("2/5 — Déduplication ignorée (dry-run)")

    print("3/5 — Pré-filtrage thématique...")
    items = pre_filter(items, profile.topics, threshold=0.08)
    print(f"    {len(items)} items après filtre")

    if dry_run:
        print("4/5 — Extraction et analyse ignorées (dry-run)")
        print("5/5 — Dry-run terminé.")
        return []

    print("4/5 — Extraction full-text (Jina Reader)...")
    fulltext: dict[str, str] = {}
    for item in items:
        if len(item.summary) < 100:
            fulltext[item.uid] = fetch_fulltext(item.url)
    print(f"    {len(fulltext)} full-texts extraits")

    print("5/5 — Analyse Claude (batch)...")
    scored_all = []
    batch_size = config.claude_batch_size
    total_batches = max(1, (len(items) - 1) // batch_size + 1)
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        scored_all += analyze_batch(
            batch,
            profile,
            fulltext,
            model=config.claude_model,
        )
        print(f"    Batch {i // batch_size + 1}/{total_batches} analysé")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = date.today().strftime("%Y-W%W")

    html = generate_html_briefing(scored_all, config)
    md = generate_markdown_briefing(scored_all, config)

    (output_dir / f"{stem}.html").write_text(html, encoding="utf-8")
    (output_dir / f"{stem}.md").write_text(md, encoding="utf-8")
    print(f"Briefing sauvegardé : {output_dir / stem}.*")

    mark_seen(items, db_path)

    if email_to:
        send_email(html, to=email_to, subject=f"Veille tech {stem}")

    return scored_all


def main() -> None:
    """Point d'entrée CLI enregistré dans ``pyproject.toml``."""
    parser = argparse.ArgumentParser(
        description="Agent de veille technologique hebdomadaire"
    )
    parser.add_argument(
        "--email",
        metavar="ADRESSE",
        help="Envoyer le briefing à cette adresse email",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collecter et filtrer sans appeler Claude ni écrire en base",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Dossier de sortie pour les briefings (défaut : data/briefings/)",
    )
    args = parser.parse_args()

    try:
        log_path = _get_package_dir("log")
        data_path = _get_package_dir("data")
        config_path = _get_package_dir("config")
    except NameError:
        sys.exit(1)

    _setup_logging(log_path)

    db_path = str(data_path / "watch.db")
    output_dir = Path(args.output_dir) if args.output_dir else data_path / "briefings"

    config = WatchConfig()
    profile = load_profile(config_path / "profile.yaml")

    try:
        run(
            config=config,
            profile=profile,
            db_path=db_path,
            output_dir=output_dir,
            email_to=args.email,
            dry_run=args.dry_run,
        )
    except Exception:
        logging.exception("Erreur fatale lors de l'exécution de l'agent.")
        sys.exit(1)


if __name__ == "__main__":
    main()
