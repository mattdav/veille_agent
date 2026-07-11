"""Tests pour bin/mailer.py."""

from unittest.mock import MagicMock, patch

import pytest
from pytest import MonkeyPatch

from veille_agent.bin.mailer import send_email


def test_send_email_success(monkeypatch: MonkeyPatch) -> None:
    """Un envoi réussi doit ouvrir la session SMTP et logguer/appeler login."""
    monkeypatch.setenv("GMAIL_FROM", "moi@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcdabcdabcdabcd")
    smtp_instance = MagicMock()
    smtp_cm = MagicMock()
    smtp_cm.__enter__.return_value = smtp_instance
    with patch("veille_agent.bin.mailer.smtplib.SMTP", return_value=smtp_cm):
        send_email("<p>Salut</p>", to="dest@example.com", subject="Test")
    smtp_instance.login.assert_called_once_with("moi@gmail.com", "abcdabcdabcdabcd")
    smtp_instance.send_message.assert_called_once()


def test_send_email_missing_env_raises(monkeypatch: MonkeyPatch) -> None:
    """L'absence des variables d'environnement Gmail doit lever KeyError."""
    monkeypatch.delenv("GMAIL_FROM", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    with pytest.raises(KeyError):
        send_email("<p>Salut</p>", to="dest@example.com", subject="Test")
