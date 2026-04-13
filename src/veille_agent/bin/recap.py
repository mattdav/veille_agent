"""Recap mensuel Top-K : tendances structurantes des 4 dernières semaines."""

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from anthropic.types import TextBlock

from veille_agent.bin.analyst import ANALYST_SYSTEM, ScoredItem, _get_client
from veille_agent.bin.config import WatchConfig
from veille_agent.bin.profile import UserProfile

_RECAP_SYSTEM = (
    "Tu es un analyste technologique expert.\n"
    "Tu synthétises des tendances à partir d'articles sélectionnés "
    "et retournes UNIQUEMENT du JSON valide, sans markdown, sans commentaires."
)


# ---------------------------------------------------------------------------
# Persistance des ScoredItems en base SQLite
# ---------------------------------------------------------------------------


def persist_scored_items(
    scored_items: list[ScoredItem],
    week_label: str,
    db_path: str,
) -> None:
    """Persiste les articles scorés en base pour le recap mensuel.

    Stocke uniquement les articles dont la pertinence est >= 6 pour
    ne pas encombrer la base avec du bruit.

    Args:
        scored_items: Articles analysés cette semaine.
        week_label: Étiquette de semaine au format ``YYYY-WNN``.
        db_path: Chemin vers la base SQLite.

    Examples:
        >>> persist_scored_items([], "2025-W01", ":memory:")
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS briefing_items (
            uid          TEXT NOT NULL,
            week         TEXT NOT NULL,
            title        TEXT,
            url          TEXT,
            source       TEXT,
            relevance    REAL,
            summary_fr   TEXT,
            poc_idea     TEXT,
            tags         TEXT,
            why_relevant TEXT,
            deepdive     TEXT,
            created_at   TEXT,
            PRIMARY KEY (uid, week)
        )
        """
    )
    rows = [
        (
            s.item.uid,
            week_label,
            s.item.title,
            s.item.url,
            s.item.source,
            s.relevance,
            s.summary_fr,
            s.poc_idea,
            json.dumps(s.tags, ensure_ascii=False),
            s.why_relevant,
            s.deepdive,
            datetime.now().isoformat(),
        )
        for s in scored_items
        if s.relevance >= 6.0
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO briefing_items
        (uid, week, title, url, source, relevance, summary_fr,
         poc_idea, tags, why_relevant, deepdive, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    logging.info(
        "persist_scored_items: %d articles persistés pour %s", len(rows), week_label
    )


def load_recent_scored_items(
    db_path: str,
    since_weeks: int = 4,
) -> list[dict[str, Any]]:
    """Charge les articles des N dernières semaines depuis SQLite.

    Args:
        db_path: Chemin vers la base SQLite.
        since_weeks: Fenêtre en semaines (défaut : 4).

    Returns:
        Liste de dicts représentant les articles persistés.

    Examples:
        >>> load_recent_scored_items(":memory:", since_weeks=4)
        []
    """
    cutoff = (datetime.now() - timedelta(weeks=since_weeks)).strftime("%Y-W%W")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS briefing_items "
            "(uid TEXT, week TEXT, title TEXT, url TEXT, source TEXT, "
            "relevance REAL, summary_fr TEXT, poc_idea TEXT, tags TEXT, "
            "why_relevant TEXT, deepdive TEXT, created_at TEXT, "
            "PRIMARY KEY (uid, week))"
        )
        rows = conn.execute(
            """
            SELECT title, url, source, relevance, summary_fr, poc_idea, tags
            FROM briefing_items
            WHERE week >= ?
            ORDER BY relevance DESC
            """,
            (cutoff,),
        ).fetchall()
        conn.close()
    except sqlite3.OperationalError:
        return []

    return [
        {
            "title": r[0],
            "url": r[1],
            "source": r[2],
            "relevance": r[3],
            "summary_fr": r[4],
            "poc_idea": r[5],
            "tags": json.loads(r[6]) if r[6] else [],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Génération du recap par Claude
# ---------------------------------------------------------------------------


def _build_recap_prompt(
    articles: list[dict[str, Any]],
    profile: UserProfile,
    since_weeks: int,
) -> str:
    """Construit le prompt de recap mensuel.

    Args:
        articles: Articles des N dernières semaines.
        profile: Profil utilisateur.
        since_weeks: Nombre de semaines couvertes.

    Returns:
        Prompt prêt à envoyer à Claude.

    Examples:
        >>> from veille_agent.bin.profile import UserProfile
        >>> p = UserProfile(
        ...     topics=["dbt"],
        ...     context="Dev Python.",
        ...     scoring_high="h",
        ...     scoring_medium="m",
        ...     scoring_low="l",
        ...     threshold=6.0,
        ... )
        >>> prompt = _build_recap_prompt([], p, 4)
        >>> "tendances" in prompt
        True
    """
    return (
        f"Contexte du développeur :\n{profile.context}\n\n"
        f"Voici {len(articles)} articles retenus lors des {since_weeks} "
        "dernières semaines de veille technologique :\n"
        f"{json.dumps(articles, ensure_ascii=False, indent=2)}\n\n"
        "Analyse ces articles et identifie les 5 tendances technologiques "
        "structurantes de cette période.\n\n"
        "Pour chaque tendance, retourne un objet JSON avec :\n"
        '- "title": titre court de la tendance (max 8 mots)\n'
        '- "description": explication en 3-4 phrases en français\n'
        '- "why_matters": pourquoi c\'est important pour ce développeur '
        "(1-2 phrases)\n"
        '- "poc_ideas": liste de 1-2 idées de POC concrètes\n'
        '- "key_articles": liste des URLs des 2-3 articles les plus '
        "représentatifs\n\n"
        "Retourne un JSON array de 5 objets. Rien d'autre."
    )


def generate_monthly_recap(
    db_path: str,
    profile: UserProfile,
    config: WatchConfig,
    output_dir: Path,
    since_weeks: int = 4,
    email_to: str | None = None,
) -> list[dict[str, Any]]:
    """Génère le recap mensuel Top-K des tendances structurantes.

    Charge les articles des ``since_weeks`` dernières semaines depuis
    SQLite, demande à Claude d'en extraire les tendances, puis génère
    un rapport HTML et Markdown dans ``output_dir``.

    Args:
        db_path: Chemin vers la base SQLite.
        profile: Profil utilisateur.
        config: Configuration de l'agent.
        output_dir: Dossier de sortie.
        since_weeks: Fenêtre d'analyse en semaines (défaut : 4).
        email_to: Si fourni, envoie le rapport par email.

    Returns:
        Liste des tendances générées (dicts JSON).

    Examples:
        >>> from pathlib import Path
        >>> from veille_agent.bin.config import WatchConfig
        >>> from veille_agent.bin.profile import UserProfile
        >>> p = UserProfile(
        ...     topics=["dbt"],
        ...     context="Dev Python.",
        ...     scoring_high="h",
        ...     scoring_medium="m",
        ...     scoring_low="l",
        ...     threshold=6.0,
        ... )
        >>> cfg = WatchConfig()
        >>> generate_monthly_recap(":memory:", p, cfg, Path("/tmp"), since_weeks=4)
        []
    """
    articles = load_recent_scored_items(db_path, since_weeks=since_weeks)
    if not articles:
        logging.warning("generate_monthly_recap: aucun article en base — recap ignoré.")
        return []

    print(
        f"Recap mensuel : {len(articles)} articles analysés sur {since_weeks} semaines..."
    )

    prompt = _build_recap_prompt(articles, profile, since_weeks)
    response = _get_client().messages.create(
        model=config.claude_model,
        max_tokens=3000,
        system=_RECAP_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = cast(TextBlock, response.content[0]).text

    try:
        trends: list[dict[str, Any]] = json.loads(raw_text)
    except json.JSONDecodeError:
        logging.error("generate_monthly_recap: JSON invalide.\n%s", raw_text[:500])
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"recap-{date.today().strftime('%Y-%m')}"

    html = _render_recap_html(trends, since_weeks)
    md = _render_recap_markdown(trends, since_weeks)

    (output_dir / f"{stem}.html").write_text(html, encoding="utf-8")
    (output_dir / f"{stem}.md").write_text(md, encoding="utf-8")
    print(f"Recap sauvegardé : {output_dir / stem}.*")

    if email_to:
        from veille_agent.bin.mailer import send_email

        send_email(
            html,
            to=email_to,
            subject=f"Recap veille tech — {date.today().strftime('%B %Y')}",
        )

    return trends


# ---------------------------------------------------------------------------
# Rendu HTML / Markdown du recap
# ---------------------------------------------------------------------------


def _render_recap_html(trends: list[dict[str, Any]], since_weeks: int) -> str:
    """Rend les tendances en HTML autonome.

    Args:
        trends: Liste de dicts de tendances générés par Claude.
        since_weeks: Fenêtre couverte, pour le titre.

    Returns:
        Chaîne HTML complète.

    Examples:
        >>> html = _render_recap_html([], 4)
        >>> "<html" in html
        True
    """
    month = date.today().strftime("%B %Y")
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Recap veille — {month}</title>
<style>
  body {{
    font-family: system-ui, sans-serif; max-width: 760px;
    margin: 2rem auto; color: #1a1a1a; line-height: 1.6;
  }}
  h1 {{
    font-size: 1.4rem; font-weight: 600;
    border-bottom: 2px solid #eee; padding-bottom: .5rem;
  }}
  .trend {{
    margin: 1.5rem 0; padding: 1.2rem;
    border: 1px solid #e8e8e8; border-radius: 8px;
    border-left: 4px solid #6366f1;
  }}
  .trend-title {{ font-size: 1.05rem; font-weight: 600; margin-bottom: .5rem; }}
  .trend-desc {{ font-size: .9rem; margin-bottom: .5rem; }}
  .trend-why {{
    font-size: .85rem; color: #555; font-style: italic; margin-bottom: .5rem;
  }}
  .poc-list {{ font-size: .85rem; margin: .4rem 0 .4rem 1rem; }}
  .sources {{ font-size: .78rem; color: #6b7280; margin-top: .5rem; }}
  .sources a {{ color: #6b7280; }}
</style>
</head>
<body>
<h1>Recap veille tech — {month}</h1>
<p style="color:#666;font-size:.9rem">
  Synthèse des {since_weeks} dernières semaines — {len(trends)} tendances identifiées
</p>
"""
    for i, trend in enumerate(trends, 1):
        pocs = trend.get("poc_ideas", [])
        pocs_html = "".join(f"<li>{p}</li>" for p in pocs)
        sources = trend.get("key_articles", [])
        sources_html = " · ".join(
            f'<a href="{u}" target="_blank">[{j + 1}]</a>'
            for j, u in enumerate(sources)
        )
        html += f"""
<div class="trend">
  <div class="trend-title">{i}. {trend.get("title", "")}</div>
  <div class="trend-desc">{trend.get("description", "")}</div>
  <div class="trend-why">{trend.get("why_matters", "")}</div>
  <ul class="poc-list">{pocs_html}</ul>
  <div class="sources">Sources : {sources_html}</div>
</div>"""

    html += "\n</body>\n</html>\n"
    return html


def _render_recap_markdown(trends: list[dict[str, Any]], since_weeks: int) -> str:
    """Rend les tendances en Markdown.

    Args:
        trends: Liste de dicts de tendances générés par Claude.
        since_weeks: Fenêtre couverte, pour le titre.

    Returns:
        Chaîne Markdown.

    Examples:
        >>> md = _render_recap_markdown([], 4)
        >>> "Recap" in md
        True
    """
    month = date.today().strftime("%Y-%m")
    lines = [
        f"# Recap veille tech {month}\n",
        f"Synthèse des {since_weeks} dernières semaines.\n",
    ]
    for i, trend in enumerate(trends, 1):
        lines.append(f"## {i}. {trend.get('title', '')}\n")
        lines.append(trend.get("description", ""))
        lines.append(f"\n*{trend.get('why_matters', '')}*\n")
        for poc in trend.get("poc_ideas", []):
            lines.append(f"- POC : {poc}")
        for url in trend.get("key_articles", []):
            lines.append(f"- {url}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Système prompt partagé (réexporté pour les tests)
# ---------------------------------------------------------------------------

__all__ = [
    "ANALYST_SYSTEM",
    "generate_monthly_recap",
    "load_recent_scored_items",
    "persist_scored_items",
]
