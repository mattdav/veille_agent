"""Tests pour bin/reader.py."""

from unittest.mock import MagicMock, patch

import httpx

from veille_agent.bin.reader import fetch_fulltext


def test_fetch_fulltext_success() -> None:
    """Une réponse 200 doit retourner le texte tronqué à max_chars."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.text = "Contenu extrait complet"
    with patch("veille_agent.bin.reader.httpx.get", return_value=fake_response):
        result = fetch_fulltext("https://example.com", max_chars=7)
    assert result == "Contenu"


def test_fetch_fulltext_non_200_returns_empty() -> None:
    """Une réponse non-200 doit retourner une chaîne vide."""
    fake_response = MagicMock()
    fake_response.status_code = 404
    with patch("veille_agent.bin.reader.httpx.get", return_value=fake_response):
        assert fetch_fulltext("https://example.com") == ""


def test_fetch_fulltext_network_error_returns_empty() -> None:
    """Une erreur réseau doit retourner une chaîne vide (dégradation gracieuse)."""
    with patch(
        "veille_agent.bin.reader.httpx.get", side_effect=httpx.RequestError("boom")
    ):
        assert fetch_fulltext("https://example.com") == ""
