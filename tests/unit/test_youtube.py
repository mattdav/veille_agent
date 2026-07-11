"""Tests pour bin/youtube.py."""

from unittest.mock import MagicMock, patch

import httpx
from pytest import MonkeyPatch

from veille_agent.bin.youtube import _resolve_channel_id, collect_youtube


def test_collect_youtube_no_channels_returns_empty() -> None:
    """Sans chaîne, aucun appel n'est effectué."""
    assert collect_youtube([]) == []


def test_collect_youtube_missing_api_key_returns_empty(
    monkeypatch: MonkeyPatch,
) -> None:
    """Sans YOUTUBE_API_KEY, la collecte est ignorée sans erreur."""
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert collect_youtube(["UCxxxx"]) == []


def test_resolve_channel_id_passthrough_for_uc_id() -> None:
    """Un identifiant déjà au format UCxxx est retourné tel quel."""
    assert _resolve_channel_id("UCabc", "fake-key") == "UCabc"


def test_resolve_channel_id_resolves_handle() -> None:
    """Un handle @NomChaine doit être résolu via l'API /channels."""
    fake_response = MagicMock()
    fake_response.json.return_value = {"items": [{"id": "UCresolved"}]}
    with patch("veille_agent.bin.youtube.httpx.get", return_value=fake_response):
        assert _resolve_channel_id("@MaChaine", "fake-key") == "UCresolved"


def test_resolve_channel_id_network_error_returns_empty() -> None:
    """Une erreur réseau lors de la résolution retourne une chaîne vide."""
    with patch(
        "veille_agent.bin.youtube.httpx.get", side_effect=httpx.RequestError("boom")
    ):
        assert _resolve_channel_id("@MaChaine", "fake-key") == ""


def test_collect_youtube_success(monkeypatch: MonkeyPatch) -> None:
    """Une réponse 200 avec une vidéo doit produire un RawItem."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "items": [
            {
                "id": {"videoId": "vid123"},
                "snippet": {
                    "title": "Titre vidéo",
                    "description": "Description courte",
                    "channelTitle": "Ma Chaîne",
                    "publishedAt": "2025-01-01T00:00:00Z",
                },
            }
        ]
    }
    with (
        patch("veille_agent.bin.youtube.httpx.get", return_value=fake_response),
        patch("veille_agent.bin.youtube.fetch_transcript", return_value=""),
    ):
        items = collect_youtube(["UCabc"], since_days=7, max_per_channel=1)
    assert len(items) == 1
    assert items[0].title == "Titre vidéo"


def test_collect_youtube_non_200_skips_channel(monkeypatch: MonkeyPatch) -> None:
    """Une réponse non-200 doit être ignorée pour la chaîne concernée."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    fake_response = MagicMock()
    fake_response.status_code = 500
    with patch("veille_agent.bin.youtube.httpx.get", return_value=fake_response):
        assert collect_youtube(["UCabc"]) == []


def test_collect_youtube_network_error_skips_channel(monkeypatch: MonkeyPatch) -> None:
    """Une erreur réseau doit être ignorée pour la chaîne concernée."""
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    with patch(
        "veille_agent.bin.youtube.httpx.get", side_effect=httpx.RequestError("boom")
    ):
        assert collect_youtube(["UCabc"]) == []
