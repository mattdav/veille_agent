"""Extraction full-text via Jina Reader (r.jina.ai)."""

import httpx


def fetch_fulltext(url: str, max_chars: int = 3000) -> str:
    """Extrait le contenu texte d'une URL via Jina Reader.

    Jina Reader (r.jina.ai) convertit n'importe quelle page web en Markdown
    propre sans nécessiter de scraping ni de clé API.

    Appelé uniquement si ``len(item.summary) < 100`` pour limiter les
    requêtes. Retourne une chaîne vide en cas d'erreur (dégradation
    gracieuse — le pipeline utilise alors le résumé RSS).

    Args:
        url: URL de l'article à extraire.
        max_chars: Nombre maximum de caractères à retourner.

    Returns:
        Contenu Markdown de la page, tronqué à ``max_chars``.

    Examples:
        >>> fetch_fulltext("not-a-url")
        ''
    """
    jina_url = f"https://r.jina.ai/{url}"
    try:
        r = httpx.get(
            jina_url,
            timeout=15,
            headers={"Accept": "text/plain"},
            follow_redirects=True,
        )
        if r.status_code == 200:
            return r.text[:max_chars]
    except httpx.RequestError:
        pass
    return ""
