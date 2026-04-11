"""Envoi du briefing par email via Gmail (SMTP + mot de passe d'application)."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


def send_email(html_body: str, to: str, subject: str) -> None:
    """Envoie le briefing HTML par email via Gmail.

    Utilise SMTP avec STARTTLS et un mot de passe d'application Gmail
    (à générer sur https://myaccount.google.com/apppasswords).

    Les paramètres sont lus depuis les variables d'environnement :

    - ``GMAIL_FROM`` : adresse Gmail expéditrice (ex: vous@gmail.com)
    - ``GMAIL_APP_PASSWORD`` : mot de passe d'application Gmail (16 caractères,
      sans espaces)

    Args:
        html_body: Contenu HTML du message.
        to: Adresse email du destinataire.
        subject: Objet du message.

    Raises:
        KeyError: Si ``GMAIL_FROM`` ou ``GMAIL_APP_PASSWORD`` ne sont pas
            définis dans l'environnement.
        smtplib.SMTPException: En cas d'erreur lors de l'envoi.

    Examples:
        >>> # Ne peut pas être testé sans compte Gmail configuré
        >>> callable(send_email)
        True
    """
    sender = os.environ["GMAIL_FROM"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(sender, password)
        smtp.send_message(msg)

    print(f"Email envoyé à {to}")
