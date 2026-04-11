"""Analyse des articles par l'API Claude et scoring de pertinence."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from veille_agent.bin.collector import RawItem
from veille_agent.bin.profile import UserProfile

ANALYST_SYSTEM = (
    "Tu es un assistant de veille technologique pour un développeur Python "
    "spécialisé en data engineering et IA.\n"
    "Tu analyses des articles et retournes UNIQUEMENT du JSON valide, "
    "sans markdown, sans commentaires."
)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Retourne le client Anthropic (singleton lazy)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


@dataclass
class ScoredItem:
    """Article analysé et scoré par Claude.

    Examples:
        >>> from veille_agent.bin.collector import RawItem
        >>> item = RawItem(title="t", url="https://x.com", source="s")
        >>> si = ScoredItem(item=item, relevance=7.0, summary_fr="ok",
        ...                 poc_idea="", tags=["dbt"], why_relevant="utile")
        >>> si.relevance
        7.0
    """

    item: RawItem
    relevance: float
    summary_fr: str
    poc_idea: str
    tags: list[str] = field(default_factory=list)
    why_relevant: str = ""


def _build_prompt(
    articles_payload: list[dict[str, Any]],
    profile: UserProfile,
) -> str:
    """Construit le prompt d'analyse à partir du profil et des articles.

    Args:
        articles_payload: Liste de dicts sérialisables décrivant les articles.
        profile: Profil utilisateur chargé depuis ``profile.yaml``.

    Returns:
        Prompt complet prêt à être envoyé à Claude.

    Examples:
        >>> from veille_agent.bin.profile import UserProfile
        >>> p = UserProfile(
        ...     topics=["dbt"],
        ...     context="Dev Python.",
        ...     scoring_high="utilisable",
        ...     scoring_medium="moyen terme",
        ...     scoring_low="eloigne",
        ...     threshold=6.0,
        ... )
        >>> prompt = _build_prompt([], p)
        >>> "dbt" in prompt
        True
    """
    return (
        f"Thématiques d'intérêt : {', '.join(profile.topics)}\n\n"
        f"Contexte du développeur :\n{profile.context}\n\n"
        "Critères de scoring :\n"
        f"- Score 9-10 : {profile.scoring_high}\n"
        f"- Score 6-8  : {profile.scoring_medium}\n"
        f"- Score < 6  : {profile.scoring_low}\n\n"
        f"Articles à analyser :\n"
        f"{json.dumps(articles_payload, ensure_ascii=False, indent=2)}\n\n"
        "Pour chaque article, retourne un objet JSON avec :\n"
        "- \"id\": l'uid de l'article\n"
        '- "relevance": note de 0 à 10 selon les critères ci-dessus\n'
        '- "summary_fr": résumé en 2-3 phrases en français\n'
        '- "poc_idea": idée de POC concret en 1 phrase (sinon "")\n'
        '- "tags": liste de 1-3 tags parmi les thématiques\n'
        '- "why_relevant": en 1 phrase, pourquoi utile'
        ' (ou "Hors sujet" si score < 4)\n\n'
        "Retourne un JSON array. Rien d'autre."
    )


def analyze_batch(
    items: list[RawItem],
    profile: UserProfile,
    fulltext: dict[str, str],
    model: str = "claude-sonnet-4-20250514",
) -> list[ScoredItem]:
    """Analyse un batch d'articles via l'API Claude.

    Traite jusqu'à 20 items en un seul appel pour maîtriser les coûts.
    Le JSON retourné par Claude est parsé et converti en :class:`ScoredItem`.

    **Format de sortie attendu de Claude** (ne pas modifier sans mettre à
    jour le parsing) ::

        [
          {
            "id": "uid_md5",
            "relevance": 8,
            "summary_fr": "...",
            "poc_idea": "...",
            "tags": ["dbt", "python"],
            "why_relevant": "..."
          }
        ]

    Args:
        items: Articles à analyser.
        profile: Profil utilisateur chargé depuis ``profile.yaml``.
        fulltext: Dict ``{uid: texte_extrait}`` pour les articles sans résumé.
        model: Identifiant du modèle Claude à utiliser.

    Returns:
        Liste de :class:`ScoredItem` triée par pertinence décroissante.

    Examples:
        >>> from veille_agent.bin.profile import UserProfile
        >>> p = UserProfile(
        ...     topics=["dbt"],
        ...     context="Dev Python.",
        ...     scoring_high="utilisable",
        ...     scoring_medium="moyen terme",
        ...     scoring_low="eloigne",
        ...     threshold=6.0,
        ... )
        >>> analyze_batch([], p, {})
        []
    """
    if not items:
        return []

    articles_payload = [
        {
            "id": item.uid,
            "title": item.title,
            "source": item.source,
            "summary": item.summary,
            "fulltext_excerpt": fulltext.get(item.uid, "")[:1500],
        }
        for item in items
    ]

    prompt = _build_prompt(articles_payload, profile)

    response = _get_client().messages.create(
        model=model,
        max_tokens=4000,
        system=ANALYST_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text  # type: ignore[union-attr]

    # Claude peut exceptionnellement envelopper le JSON dans des fences Markdown
    # (```json … ```) malgré les instructions du system prompt — on les retire.
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()
        raw_text = stripped

    if not raw_text:
        logging.warning("analyze_batch: réponse Claude vide — batch ignoré.")
        return []

    try:
        results_raw: list[dict[str, Any]] = json.loads(raw_text)
    except json.JSONDecodeError:
        logging.warning(
            "analyze_batch: JSON invalide dans la réponse Claude — batch ignoré.\n%s",
            raw_text[:500],
        )
        return []

    item_by_uid = {i.uid: i for i in items}

    scored: list[ScoredItem] = []
    for r in results_raw:
        uid = r.get("id", "")
        if uid not in item_by_uid:
            continue
        scored.append(
            ScoredItem(
                item=item_by_uid[uid],
                relevance=float(r.get("relevance", 0)),
                summary_fr=r.get("summary_fr", ""),
                poc_idea=r.get("poc_idea", ""),
                tags=r.get("tags", []),
                why_relevant=r.get("why_relevant", ""),
            )
        )

    return sorted(scored, key=lambda x: x.relevance, reverse=True)
