"""Fixtures pytest partagées entre les modules de tests."""

import pytest

from veille_agent.bin.analyst import ScoredItem
from veille_agent.bin.collector import RawItem
from veille_agent.bin.profile import UserProfile


@pytest.fixture
def profile() -> UserProfile:
    """Profil utilisateur minimal pour les tests."""
    return UserProfile(
        topics=["dbt", "python"],
        context="Dev Python senior.",
        scoring_high="utilisable cette semaine",
        scoring_medium="applicable à moyen terme",
        scoring_low="trop éloigné",
        threshold=6.0,
        rss_feeds=[{"name": "Hacker News", "url": "https://hnrss.org/best"}],
        arxiv_categories=["cs.AI"],
        github_topics=["llm"],
        youtube_channels=["@PyCon"],
    )


@pytest.fixture
def raw_item() -> RawItem:
    """Article brut minimal pour les tests."""
    return RawItem(
        title="Un article test",
        url="https://example.com/article",
        source="Test",
        summary="Résumé court.",
    )


@pytest.fixture
def scored_item(raw_item: RawItem) -> ScoredItem:
    """Article scoré minimal pour les tests."""
    return ScoredItem(
        item=raw_item,
        relevance=8.5,
        summary_fr="Résumé en français.",
        poc_idea="Construire un POC.",
        tags=["dbt", "python"],
        why_relevant="Directement applicable.",
    )
