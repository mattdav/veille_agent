"""Tests pour bin/collector.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from veille_agent.bin.collector import (
    RawItem,
    collect_arxiv,
    collect_github_trending,
    collect_rss,
    deduplicate,
    mark_seen,
)


def test_collect_rss_maps_fields_from_entries() -> None:
    """Un flux RSS avec une entrée doit être converti en RawItem."""
    fake_entry = {
        "title": "Titre récent",
        "link": "https://example.com/1",
        "summary": "résumé",
    }
    fake_feed = MagicMock()
    fake_feed.entries = [fake_entry]
    with patch("veille_agent.bin.collector.feedparser.parse", return_value=fake_feed):
        items = collect_rss(
            [{"name": "Src", "url": "https://x.com/feed"}], since_days=7
        )
    assert len(items) == 1
    assert items[0].title == "Titre récent"
    assert items[0].source == "Src"


def test_collect_arxiv_empty_categories_returns_empty() -> None:
    """Sans catégorie, aucun appel réseau n'est effectué."""
    assert collect_arxiv([]) == []


def test_collect_arxiv_maps_entries() -> None:
    """Les entrées arXiv doivent être converties en RawItem, titre nettoyé."""
    entry = MagicMock()
    entry.title = "Papier\nsur deux lignes"
    entry.id = "https://arxiv.org/abs/1234"
    entry.summary = "résumé du papier"
    entry.published = "2025-01-01"
    fake_feed = MagicMock()
    fake_feed.entries = [entry]
    with patch("veille_agent.bin.collector.feedparser.parse", return_value=fake_feed):
        items = collect_arxiv(["cs.AI"])
    assert items[0].source == "arXiv"
    assert "\n" not in items[0].title


def test_collect_github_trending_empty_topics_returns_empty() -> None:
    """Sans topic, aucun appel réseau n'est effectué."""
    assert collect_github_trending([]) == []


def test_collect_github_trending_success() -> None:
    """Une réponse 200 avec des dépôts doit produire des RawItem."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "items": [
            {
                "full_name": "org/repo",
                "html_url": "https://github.com/org/repo",
                "description": "Un super projet",
                "stargazers_count": 42,
            }
        ]
    }
    with patch("veille_agent.bin.collector.httpx.get", return_value=fake_response):
        items = collect_github_trending(["llm"])
    assert len(items) == 1
    assert "org/repo" in items[0].title


def test_collect_github_trending_non_200_ignored() -> None:
    """Une réponse non-200 doit être ignorée sans erreur."""
    fake_response = MagicMock()
    fake_response.status_code = 500
    with patch("veille_agent.bin.collector.httpx.get", return_value=fake_response):
        assert collect_github_trending(["llm"]) == []


def test_collect_github_trending_network_error_ignored() -> None:
    """Une erreur réseau doit être ignorée sans erreur (dégradation gracieuse)."""
    with patch(
        "veille_agent.bin.collector.httpx.get",
        side_effect=httpx.RequestError("boom"),
    ):
        assert collect_github_trending(["llm"]) == []


def test_deduplicate_and_mark_seen(tmp_path: Path) -> None:
    """Un item marqué comme vu doit être exclu d'une déduplication ultérieure."""
    db_path = str(tmp_path / "watch.db")
    item = RawItem(title="t", url="https://example.com/x", source="s")
    assert deduplicate([item], db_path=db_path) == [item]
    mark_seen([item], db_path=db_path)
    assert deduplicate([item], db_path=db_path) == []
