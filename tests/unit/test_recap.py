"""Tests pour bin/recap.py."""

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from pytest import MonkeyPatch

from veille_agent.bin.analyst import ScoredItem
from veille_agent.bin.collector import RawItem
from veille_agent.bin.profile import UserProfile
from veille_agent.bin.recap import (
    generate_monthly_recap,
    load_recent_scored_items,
    persist_scored_items,
)


def _profile() -> UserProfile:
    return UserProfile(
        topics=["dbt"],
        context="Dev Python.",
        scoring_high="h",
        scoring_medium="m",
        scoring_low="l",
        threshold=6.0,
    )


def _fake_text_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def _current_week_label() -> str:
    return datetime.now().strftime("%Y-W%W")


def test_persist_and_load_scored_items(tmp_path: Path) -> None:
    """Un article persisté au-dessus du seuil doit être rechargé ensuite."""
    db_path = str(tmp_path / "watch.db")
    raw = RawItem(title="t", url="https://x.com", source="s")
    scored = ScoredItem(
        item=raw, relevance=8.0, summary_fr="ok", poc_idea="", tags=["dbt"]
    )
    persist_scored_items([scored], _current_week_label(), db_path, threshold=6.0)
    loaded = load_recent_scored_items(db_path, since_weeks=52)
    assert len(loaded) == 1
    assert loaded[0]["title"] == "t"
    assert loaded[0]["tags"] == ["dbt"]


def test_persist_scored_items_below_threshold_not_persisted(tmp_path: Path) -> None:
    """Un article sous le seuil ne doit pas être persisté."""
    db_path = str(tmp_path / "watch.db")
    raw = RawItem(title="t", url="https://x.com", source="s")
    scored = ScoredItem(item=raw, relevance=3.0, summary_fr="ok", poc_idea="")
    persist_scored_items([scored], _current_week_label(), db_path, threshold=6.0)
    assert load_recent_scored_items(db_path, since_weeks=52) == []


def test_generate_monthly_recap_no_articles_returns_empty(tmp_path: Path) -> None:
    """Sans article en base, le recap est ignoré."""
    db_path = str(tmp_path / "watch.db")
    result = generate_monthly_recap(db_path, _profile(), tmp_path, since_weeks=4)
    assert result == []


def test_generate_monthly_recap_success(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Un article en base et une réponse JSON valide doivent produire un recap."""
    monkeypatch.setenv("CLAUDE_MODEL_DEEPDIVE", "claude-sonnet-5")
    db_path = str(tmp_path / "watch.db")
    raw = RawItem(title="t", url="https://x.com", source="s")
    scored = ScoredItem(item=raw, relevance=9.0, summary_fr="ok", poc_idea="")
    persist_scored_items([scored], _current_week_label(), db_path, threshold=6.0)

    trends = [
        {
            "title": "Tendance test",
            "description": "Description.",
            "why_matters": "Important.",
            "poc_ideas": ["Faire un POC"],
            "key_articles": ["https://x.com"],
        }
    ]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_text_response(json.dumps(trends))
    with patch("veille_agent.bin.recap._get_client", return_value=fake_client):
        result = generate_monthly_recap(db_path, _profile(), tmp_path, since_weeks=52)

    assert result == trends
    assert (tmp_path / f"recap-{date.today().strftime('%Y-%m')}.html").exists()


def test_generate_monthly_recap_invalid_json_returns_empty(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Une réponse non-JSON doit être ignorée et retourner une liste vide."""
    monkeypatch.setenv("CLAUDE_MODEL_DEEPDIVE", "claude-sonnet-5")
    db_path = str(tmp_path / "watch.db")
    raw = RawItem(title="t", url="https://x.com", source="s")
    scored = ScoredItem(item=raw, relevance=9.0, summary_fr="ok", poc_idea="")
    persist_scored_items([scored], _current_week_label(), db_path, threshold=6.0)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_text_response("pas du json")
    with patch("veille_agent.bin.recap._get_client", return_value=fake_client):
        result = generate_monthly_recap(db_path, _profile(), tmp_path, since_weeks=52)
    assert result == []
