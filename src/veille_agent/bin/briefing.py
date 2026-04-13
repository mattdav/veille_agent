"""Génération des livrables : briefing HTML et Markdown."""

from datetime import date

from veille_agent.bin.analyst import ScoredItem
from veille_agent.bin.config import WatchConfig

_CSS = """
  body {
    font-family: system-ui, sans-serif; max-width: 760px;
    margin: 2rem auto; color: #1a1a1a; line-height: 1.6;
  }
  h1 {
    font-size: 1.4rem; font-weight: 600;
    border-bottom: 2px solid #eee; padding-bottom: .5rem;
  }
  h2 { font-size: 1rem; font-weight: 600; color: #444; margin-top: 2rem; }
  h3 { font-size: .92rem; font-weight: 600; color: #333; margin: .75rem 0 .25rem; }
  .item {
    margin: 1.2rem 0; padding: 1rem;
    border: 1px solid #e8e8e8; border-radius: 8px;
  }
  .item-title { font-weight: 500; font-size: .95rem; }
  .item-title a { color: #1a1a1a; text-decoration: none; }
  .item-title a:hover { text-decoration: underline; }
  .score {
    display: inline-block; background: #f0fdf4;
    color: #166534; font-size: .75rem;
    padding: 2px 8px; border-radius: 12px; margin-left: 8px;
  }
  .score.high { background: #fef9c3; color: #854d0e; }
  .score.top { background: #fce7f3; color: #9d174d; }
  .meta { font-size: .8rem; color: #666; margin: .3rem 0; }
  .summary { font-size: .88rem; margin: .5rem 0; }
  .poc {
    background: #eff6ff; border-left: 3px solid #3b82f6;
    padding: .5rem .75rem; font-size: .85rem;
    margin-top: .5rem; border-radius: 0 6px 6px 0;
  }
  .deepdive {
    background: #faf5ff; border-left: 3px solid #7c3aed;
    padding: .75rem 1rem; font-size: .85rem;
    margin-top: .75rem; border-radius: 0 6px 6px 0;
  }
  .deepdive-title {
    font-size: .8rem; font-weight: 600; color: #6d28d9;
    margin-bottom: .4rem; text-transform: uppercase; letter-spacing: .05em;
  }
  .tag {
    display: inline-block; background: #f3f4f6;
    color: #374151; font-size: .72rem;
    padding: 1px 6px; border-radius: 4px; margin-right: 4px;
  }
"""


def generate_html_briefing(
    scored_items: list[ScoredItem], config: WatchConfig
) -> str:
    """Génère un briefing HTML autonome (CSS intégré, pas de CDN).

    Inclut la section deepdive pour les articles dont le champ
    ``ScoredItem.deepdive`` est renseigné.

    Args:
        scored_items: Articles scorés et triés par pertinence.
        config: Configuration pour les seuils et plafonds.

    Returns:
        Chaîne HTML complète prête à écrire sur disque ou envoyer par email.

    Examples:
        >>> cfg = WatchConfig()
        >>> html = generate_html_briefing([], cfg)
        >>> "<html" in html
        True
    """
    top = [
        s
        for s in scored_items
        if s.relevance >= config.min_relevance_score
    ][: config.max_items_per_briefing]

    poc_items = [s for s in top if s.poc_idea]
    deepdive_items = [s for s in top if s.deepdive]
    week = date.today().strftime("%W — %d %B %Y")

    html = (
        f'<!DOCTYPE html>\n<html lang="fr">\n<head>\n'
        f'<meta charset="UTF-8">\n'
        f"<title>Veille tech — Semaine {week}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        f"<h1>Veille tech — Semaine {week}</h1>\n"
        f'<p style="color:#666;font-size:.9rem">'
        f"{len(top)} articles retenus sur {len(scored_items)} collectés"
        f" — {len(poc_items)} idées de POC"
        f" — {len(deepdive_items)} deepdives</p>\n"
    )

    if poc_items:
        html += "<h2>Idées de POC cette semaine</h2><ul>\n"
        for s in poc_items[:5]:
            tag = s.tags[0] if s.tags else ""
            html += (
                f"  <li><strong>{tag}</strong> — {s.poc_idea} "
                f'<a href="{s.item.url}" '
                'style="color:#6b7280;font-size:.8rem">→ source</a></li>\n'
            )
        html += "</ul>\n"

    html += "<h2>Articles retenus</h2>\n"
    for s in top:
        if s.relevance >= 9:
            score_cls = "top"
        elif s.relevance >= 8:
            score_cls = "high"
        else:
            score_cls = ""

        tags_html = "".join(f'<span class="tag">{t}</span>' for t in s.tags)
        poc_html = (
            f'<div class="poc">POC : {s.poc_idea}</div>\n' if s.poc_idea else ""
        )
        deepdive_html = ""
        if s.deepdive:
            # Conversion minimale Markdown → HTML pour le deepdive
            dd_body = (
                s.deepdive.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n\n", "</p><p>")
            )
            deepdive_html = (
                '<div class="deepdive">'
                '<div class="deepdive-title">Analyse approfondie</div>'
                f"<p>{dd_body}</p>"
                "</div>\n"
            )

        html += (
            '<div class="item">\n'
            f'  <div class="item-title">'
            f'<a href="{s.item.url}" target="_blank">{s.item.title}</a>'
            f'<span class="score {score_cls}">{s.relevance:.0f}/10</span>'
            "</div>\n"
            f'  <div class="meta">'
            f"{s.item.source} · {s.item.published[:10]} · {tags_html}"
            "</div>\n"
            f'  <div class="summary">{s.summary_fr}</div>\n'
            f'  <div style="font-size:.8rem;color:#6b7280;font-style:italic">'
            f"{s.why_relevant}</div>\n"
            f"  {poc_html}"
            f"  {deepdive_html}"
            "</div>\n"
        )

    html += "</body>\n</html>\n"
    return html


def generate_markdown_briefing(
    scored_items: list[ScoredItem], config: WatchConfig
) -> str:
    """Génère un briefing Markdown compatible Obsidian / Notion.

    Inclut le deepdive en section repliable (bloc ``<details>``) pour
    les articles concernés.

    Args:
        scored_items: Articles scorés et triés par pertinence.
        config: Configuration pour les seuils et plafonds.

    Returns:
        Chaîne Markdown.

    Examples:
        >>> cfg = WatchConfig()
        >>> md = generate_markdown_briefing([], cfg)
        >>> md.startswith("# Veille tech")
        True
    """
    top = [
        s
        for s in scored_items
        if s.relevance >= config.min_relevance_score
    ][: config.max_items_per_briefing]

    week = date.today().strftime("%Y-W%W")
    lines = [f"# Veille tech {week}\n"]
    poc_items = [s for s in top if s.poc_idea]

    if poc_items:
        lines.append("## Idées de POC\n")
        for s in poc_items:
            tag = s.tags[0] if s.tags else "tech"
            lines.append(f"- **{tag}** — {s.poc_idea}")
        lines.append("")

    lines.append("## Articles\n")
    for s in top:
        hashtags = " ".join(f"#{t}" for t in s.tags)
        lines.append(
            f"### [{s.item.title}]({s.item.url}) `{s.relevance:.0f}/10`"
        )
        lines.append(f"*{s.item.source} · {hashtags}*\n")
        lines.append(s.summary_fr)
        if s.poc_idea:
            lines.append(f"\n> POC : {s.poc_idea}")
        if s.deepdive:
            lines.append("\n<details>")
            lines.append("<summary>Analyse approfondie</summary>\n")
            lines.append(s.deepdive)
            lines.append("\n</details>")
        lines.append("")

    return "\n".join(lines)
