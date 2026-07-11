"""Tests pour bin/analyst.py."""

import json
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

from veille_agent.bin.analyst import ScoredItem, analyze_batch, deepdive, run_deepdives
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


def _fake_text_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_analyze_batch_success() -> None:
    """Une réponse JSON valide doit produire des ScoredItem triés."""
    item = RawItem(title="t", url="https://x.com", source="s", summary="résumé")
    payload = json.dumps(
        [
            {
                "id": item.uid,
                "relevance": 8,
                "summary_fr": "ok",
                "poc_idea": "",
                "tags": ["dbt"],
                "why_relevant": "utile",
            }
        ]
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_text_response(payload)
    with patch("veille_agent.bin.analyst._get_client", return_value=fake_client):
        result = analyze_batch([item], _profile(), {}, model="claude-haiku-4-5")
    assert len(result) == 1
    assert result[0].relevance == 8.0


def test_analyze_batch_invalid_json_returns_empty() -> None:
    """Une réponse non-JSON doit être ignorée et retourner une liste vide."""
    item = RawItem(title="t", url="https://x.com", source="s")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_text_response("pas du json")
    with patch("veille_agent.bin.analyst._get_client", return_value=fake_client):
        result = analyze_batch([item], _profile(), {}, model="claude-haiku-4-5")
    assert result == []


def test_analyze_batch_empty_response_returns_empty() -> None:
    """Une réponse vide de Claude doit retourner une liste vide."""
    item = RawItem(title="t", url="https://x.com", source="s")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_text_response("")
    with patch("veille_agent.bin.analyst._get_client", return_value=fake_client):
        result = analyze_batch([item], _profile(), {}, model="claude-haiku-4-5")
    assert result == []


def test_analyze_batch_no_model_raises_value_error() -> None:
    """Sans modèle résolu par l'appelant, analyze_batch doit lever ValueError."""
    item = RawItem(title="t", url="https://x.com", source="s")
    with pytest.raises(ValueError, match="CLAUDE_MODEL_BATCH"):
        analyze_batch([item], _profile(), {}, model=None)


def test_deepdive_success() -> None:
    """Un bloc texte retourné par Claude doit être renvoyé tel quel."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Analyse enrichie."
    response = MagicMock()
    response.content = [text_block]
    raw = RawItem(title="t", url="https://x.com", source="s")
    scored = ScoredItem(item=raw, relevance=9.0, summary_fr="ok", poc_idea="")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = response
    with patch("veille_agent.bin.analyst._get_client", return_value=fake_client):
        result = deepdive(scored, _profile(), model="claude-sonnet-5")
    assert result == "Analyse enrichie."


def test_deepdive_api_error_returns_empty() -> None:
    """Une erreur API Claude doit être capturée et retourner une chaîne vide."""
    raw = RawItem(title="t", url="https://x.com", source="s")
    scored = ScoredItem(item=raw, relevance=9.0, summary_fr="ok", poc_idea="")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = anthropic.APIError(
        "boom", request=request, body=None
    )
    with patch("veille_agent.bin.analyst._get_client", return_value=fake_client):
        result = deepdive(scored, _profile(), model="claude-sonnet-5")
    assert result == ""


def test_deepdive_no_model_raises_value_error() -> None:
    """Sans modèle résolu par l'appelant, deepdive doit lever ValueError."""
    raw = RawItem(title="t", url="https://x.com", source="s")
    scored = ScoredItem(item=raw, relevance=9.0, summary_fr="ok", poc_idea="")
    with pytest.raises(ValueError, match="CLAUDE_MODEL_DEEPDIVE"):
        deepdive(scored, _profile(), model=None)


def test_run_deepdives_runs_for_candidates_above_threshold() -> None:
    """Seuls les articles au-dessus du seuil doivent déclencher un deepdive."""
    raw = RawItem(title="t", url="https://x.com", source="s")
    scored = ScoredItem(item=raw, relevance=9.5, summary_fr="ok", poc_idea="")
    with patch(
        "veille_agent.bin.analyst.deepdive", return_value="Analyse."
    ) as mocked_deepdive:
        result = run_deepdives(
            [scored], _profile(), model="claude-sonnet-5", threshold=9.0
        )
    mocked_deepdive.assert_called_once()
    assert result[0].deepdive == "Analyse."
