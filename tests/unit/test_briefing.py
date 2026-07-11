"""Tests pour bin/briefing.py."""

from veille_agent.bin.analyst import ScoredItem
from veille_agent.bin.briefing import (
    generate_html_briefing,
    generate_markdown_briefing,
)
from veille_agent.bin.collector import RawItem
from veille_agent.bin.profile import UserProfile


def _profile() -> UserProfile:
    return UserProfile(
        topics=["dbt"],
        context="Dev Python.",
        scoring_high="h",
        scoring_medium="m",
        scoring_low="l",
        threshold=6.0,
    )


def _scored_items() -> list[ScoredItem]:
    top_item = ScoredItem(
        item=RawItem(
            title="Top article",
            url="https://x.com/1",
            source="Src",
            published="2025-01-01T00:00:00",
        ),
        relevance=9.5,
        summary_fr="Résumé top.",
        poc_idea="Construire un POC.",
        tags=["dbt", "python"],
        why_relevant="Très utile.",
        deepdive="Paragraphe 1.\n\nParagraphe 2 avec <balise> & esperluette.",
    )
    high_item = ScoredItem(
        item=RawItem(
            title="High article",
            url="https://x.com/2",
            source="Src",
            published="2025-01-02T00:00:00",
        ),
        relevance=8.2,
        summary_fr="Résumé high.",
        poc_idea="",
        tags=[],
        why_relevant="Utile.",
    )
    return [top_item, high_item]


def test_generate_html_briefing_with_poc_and_deepdive() -> None:
    """Le HTML doit inclure la section POC, les classes de score et le deepdive."""
    html = generate_html_briefing(_scored_items(), _profile())
    assert "Idées de POC" in html
    assert "deepdive-title" in html
    assert 'class="score top"' in html
    assert 'class="score high"' in html


def test_generate_markdown_briefing_with_poc_and_deepdive() -> None:
    """Le Markdown doit inclure la section POC, les tags et le bloc deepdive."""
    md = generate_markdown_briefing(_scored_items(), _profile())
    assert "## Idées de POC" in md
    assert "<details>" in md
    assert "#dbt #python" in md
