"""Point d'entrée principal de l'agent de veille technologique.

Orchestration complète du pipeline :
    collecte → déduplication → filtrage → extraction → analyse
    → deepdive → briefing → persistance → recap mensuel (optionnel)

Usage::

    python -m veille_agent                    # run hebdomadaire complet
    python -m veille_agent --dry-run          # collecte + filtre sans Claude
    python -m veille_agent --email a@b.com    # avec envoi Gmail
    python -m veille_agent --recap            # recap mensuel uniquement
    python -m veille_agent --no-deepdive      # désactiver le deepdive
    python -m veille_agent --no-youtube       # désactiver YouTube
"""

import argparse
import importlib.resources
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from veille_agent.bin.analyst import ScoredItem, analyze_batch, run_deepdives
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
from veille_agent.bin.recap import generate_monthly_recap, persist_scored_items
from veille_agent.bin.youtube import collect_youtube

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
        package_path = Path(
            str(importlib.resources.files(f"veille_agent.{folder_name}"))
        )
        if not package_path.is_dir():
            raise NameError(f"Dossier introuvable : {folder_name}")
        return package_path
    except (ModuleNotFoundError, TypeError) as exc:
        logging.error("Le dossier %s n'existe pas.", folder_name, exc_info=True)
        raise NameError(f"Dossier introuvable : {folder_name}") from exc


def _setup_logging(log_path: Path) -> None:
    """Configure le logger applicatif vers ``log/app.log`` et stdout.

    Le StreamHandler garantit que les erreurs critiques apparaissent
    dans ``docker logs`` même si le volume log n'est pas monté.
    """
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / "app.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Fichier — toutes les entrées DEBUG+
    fh = logging.FileHandler(str(log_file))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    root.addHandler(fh)

    # Console — WARNING+ visibles dans docker logs
    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(sh)


def run(
    config: WatchConfig,
    profile: UserProfile,
    db_path: str,
    output_dir: Path,
    email_to: str | None = None,
    dry_run: bool = False,
    enable_youtube: bool = True,
    enable_deepdive: bool = True,
) -> list[ScoredItem]:
    """Exécute le pipeline hebdomadaire complet.

    Args:
        config: Paramètres techniques de l'agent.
        profile: Profil utilisateur chargé depuis ``profile.yaml``.
        db_path: Chemin vers la base SQLite.
        output_dir: Dossier de sortie pour les briefings.
        email_to: Si fourni, envoie le briefing HTML à cette adresse.
        dry_run: Collecte et filtre sans appeler Claude ni écrire en base.
        enable_youtube: Active la collecte YouTube (nécessite YOUTUBE_API_KEY).
        enable_deepdive: Active les deepdives pour les articles score >= 9.

    Returns:
        Liste des :class:`~veille_agent.bin.analyst.ScoredItem` produits.
    """
    print("1/6 — Collecte des sources...")
    items = []
    items += collect_rss(config.rss_feeds, since_days=config.rss_since_days)
    items += collect_arxiv(config.arxiv_categories)
    items += collect_github_trending(config.github_topics)
    if enable_youtube and config.youtube_channels:
        items += collect_youtube(
            config.youtube_channels,
            since_days=config.rss_since_days,
            max_per_channel=config.youtube_max_per_channel,
        )
    print(f"    {len(items)} items bruts collectés")

    if not dry_run:
        print("2/6 — Déduplication...")
        items = deduplicate(items, db_path=db_path)
        print(f"    {len(items)} nouveaux items")
    else:
        print("2/6 — Déduplication ignorée (dry-run)")

    print("3/6 — Pré-filtrage thématique...")
    items = pre_filter(items, profile.topics, threshold=0.08)
    print(f"    {len(items)} items après filtre")

    if dry_run:
        print("4/6 — Extraction et analyse ignorées (dry-run)")
        print("5/6 — Deepdive ignoré (dry-run)")
        print("6/6 — Dry-run terminé.")
        return []

    print("4/6 — Extraction full-text (Jina Reader)...")
    fulltext: dict[str, str] = {}
    for item in items:
        if len(item.summary) < 100:
            fulltext[item.uid] = fetch_fulltext(item.url)
    print(f"    {len(fulltext)} full-texts extraits")

    print("5/6 — Analyse Claude (batch)...")
    scored_all: list[ScoredItem] = []
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

    print("6/6 — Deepdive des articles top...")
    if enable_deepdive:
        scored_all = run_deepdives(
            scored_all,
            profile,
            model=config.claude_model,
            threshold=config.deepdive_threshold,
        )
    else:
        print("    Deepdive désactivé.")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = date.today().strftime("%Y-W%W")

    html = generate_html_briefing(scored_all, config)
    md = generate_markdown_briefing(scored_all, config)

    (output_dir / f"{stem}.html").write_text(html, encoding="utf-8")
    (output_dir / f"{stem}.md").write_text(md, encoding="utf-8")
    print(f"Briefing sauvegardé : {output_dir / stem}.*")

    mark_seen(items, db_path)
    persist_scored_items(scored_all, stem, db_path)

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
        help="Envoyer le briefing à cette adresse email (Gmail)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collecter et filtrer sans appeler Claude ni écrire en base",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="CHEMIN",
        help="Dossier de sortie des briefings (défaut : data/briefings/)",
    )
    parser.add_argument(
        "--no-youtube",
        action="store_true",
        help="Désactiver la collecte YouTube",
    )
    parser.add_argument(
        "--no-deepdive",
        action="store_true",
        help="Désactiver le deepdive automatique (articles score >= 9)",
    )
    parser.add_argument(
        "--recap",
        action="store_true",
        help="Générer le recap mensuel Top-K (sans run hebdomadaire)",
    )
    parser.add_argument(
        "--recap-weeks",
        type=int,
        default=None,
        metavar="N",
        help="Fenêtre du recap en semaines (défaut : config.recap_since_weeks)",
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

    # L'adresse destinataire : CLI en priorité, sinon variable d'environnement
    email_to = args.email or os.environ.get("GMAIL_TO") or None

    try:
        if args.recap:
            since_weeks = args.recap_weeks or config.recap_since_weeks
            print(f"Génération du recap mensuel ({since_weeks} semaines)...")
            generate_monthly_recap(
                db_path=db_path,
                profile=profile,
                config=config,
                output_dir=output_dir,
                since_weeks=since_weeks,
                email_to=email_to,
            )
        else:
            run(
                config=config,
                profile=profile,
                db_path=db_path,
                output_dir=output_dir,
                email_to=email_to,
                dry_run=args.dry_run,
                enable_youtube=not args.no_youtube,
                enable_deepdive=not args.no_deepdive,
            )
    except Exception:
        logging.exception("Erreur fatale lors de l'exécution de l'agent.")
        sys.exit(1)


if __name__ == "__main__":
    main()
