"""Collecte de vidéos YouTube et extraction de transcripts."""

import logging
import os
from datetime import UTC, datetime, timedelta

import httpx

from veille_agent.bin.collector import RawItem

_YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def _api_key() -> str | None:
    """Retourne la clé API YouTube depuis l'environnement."""
    return os.environ.get("YOUTUBE_API_KEY")


def fetch_transcript(video_id: str, max_chars: int = 2000) -> str:
    """Extrait le transcript d'une vidéo YouTube.

    Utilise la bibliothèque ``youtube-transcript-api`` qui récupère les
    sous-titres auto-générés ou manuels sans clé API.

    Args:
        video_id: Identifiant YouTube de la vidéo (ex: ``"dQw4w9WgXcQ"``).
        max_chars: Nombre maximum de caractères à retourner.

    Returns:
        Texte du transcript tronqué, ou chaîne vide si indisponible.

    Examples:
        >>> fetch_transcript("invalid_id_for_test")
        ''
    """
    try:
        from youtube_transcript_api import (
            NoTranscriptFound,
            YouTubeTranscriptApi,
        )

        # v1.x : YouTubeTranscriptApi s'instancie, list() remplace list_transcripts()
        transcript_list = YouTubeTranscriptApi().list(video_id)

        # Priorité : français > anglais > première langue disponible
        transcript = None
        for lang in ("fr", "en"):
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except NoTranscriptFound:
                continue

        if transcript is None:
            transcript = next(iter(transcript_list))

        # v1.x : fetch() retourne FetchedTranscript (itérable de FetchedTranscriptSnippet)
        # Les snippets exposent .text comme attribut (plus de dict)
        fetched = transcript.fetch()
        text = " ".join(snippet.text for snippet in fetched)
        return text[:max_chars]

    except Exception as exc:  # noqa: BLE001
        logging.debug("Transcript indisponible pour %s : %s", video_id, exc)
        return ""


def collect_youtube(
    channels: list[str],
    since_days: int = 7,
    max_per_channel: int = 5,
) -> list[RawItem]:
    """Collecte les vidéos récentes d'une liste de chaînes YouTube.

    Nécessite la variable d'environnement ``YOUTUBE_API_KEY``.
    Si la clé est absente, retourne une liste vide sans erreur.

    Args:
        channels: Liste d'identifiants de chaînes YouTube
            (ex: ``["UCCTVrRjpphcfzTb9vCuhHsA"]``).
            Accepte aussi les handles ``@NomDeLaChaine`` — ils sont
            résolus automatiquement via l'API.
        since_days: Fenêtre de collecte en jours.
        max_per_channel: Nombre maximum de vidéos par chaîne.

    Returns:
        Liste de :class:`~veille_agent.bin.collector.RawItem`.

    Examples:
        >>> collect_youtube([])
        []
        >>> collect_youtube(["UCtest"], since_days=7)
        []
    """
    if not channels:
        return []

    api_key = _api_key()
    if not api_key:
        logging.warning(
            "collect_youtube: YOUTUBE_API_KEY absent — collecte YouTube ignorée."
        )
        return []

    cutoff = datetime.now(tz=UTC) - timedelta(days=since_days)
    published_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    items: list[RawItem] = []

    for channel_id in channels:
        try:
            channel_id = _resolve_channel_id(channel_id, api_key)
            if not channel_id:
                continue

            params: dict[str, str | int] = {
                "key": api_key,
                "channelId": channel_id,
                "part": "snippet",
                "order": "date",
                "type": "video",
                "publishedAfter": published_after,
                "maxResults": max_per_channel,
            }
            r = httpx.get(
                f"{_YOUTUBE_API_BASE}/search",
                params=params,
                timeout=15,
            )
            if r.status_code != 200:
                logging.warning(
                    "collect_youtube: HTTP %s pour la chaîne %s",
                    r.status_code,
                    channel_id,
                )
                continue

            for video in r.json().get("items", []):
                snippet = video.get("snippet", {})
                video_id = video.get("id", {}).get("videoId", "")
                if not video_id:
                    continue

                url = f"https://www.youtube.com/watch?v={video_id}"
                description = snippet.get("description", "")[:300]
                transcript = fetch_transcript(video_id)
                summary = transcript if transcript else description

                items.append(
                    RawItem(
                        title=snippet.get("title", ""),
                        url=url,
                        source=f"YouTube/{snippet.get('channelTitle', channel_id)}",
                        summary=summary[:500],
                        published=snippet.get("publishedAt", ""),
                    )
                )

        except httpx.RequestError as exc:
            logging.warning(
                "collect_youtube: erreur réseau pour %s : %s", channel_id, exc
            )
            continue

    return items


def _resolve_channel_id(channel_ref: str, api_key: str) -> str:
    """Résout un handle ``@NomChaine`` en identifiant de chaîne YouTube.

    Si ``channel_ref`` est déjà un identifiant (commence par ``UC``),
    il est retourné tel quel.

    Args:
        channel_ref: Handle ``@NomChaine`` ou identifiant ``UCxxx``.
        api_key: Clé API YouTube Data v3.

    Returns:
        Identifiant de chaîne YouTube, ou chaîne vide si non résolu.

    Examples:
        >>> _resolve_channel_id("UCxxxxxxxxxxxxxxxxxxxxxxx", "fake")
        'UCxxxxxxxxxxxxxxxxxxxxxxx'
    """
    if channel_ref.startswith("UC"):
        return channel_ref

    handle = channel_ref.lstrip("@")
    try:
        r = httpx.get(
            f"{_YOUTUBE_API_BASE}/channels",
            params={"key": api_key, "forHandle": handle, "part": "id"},
            timeout=10,
        )
        items = r.json().get("items", [])
        if items:
            return str(items[0]["id"])
    except httpx.RequestError as exc:
        logging.warning("_resolve_channel_id: erreur pour %s : %s", handle, exc)

    return ""
