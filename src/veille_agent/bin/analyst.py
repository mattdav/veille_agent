"""Analyse des articles par l'API Claude et scoring de pertinence."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, cast

import anthropic
from anthropic.types import TextBlock

from veille_agent.bin.collector import RawItem
from veille_agent.bin.profile import UserProfile

ANALYST_SYSTEM = (
    "Tu es un assistant de veille technologique pour un développeur Python "
    "spécialisé en data engineering et IA.\n"
    "Tu analyses des articles et retournes UNIQUEMENT du JSON valide, "
    "sans markdown, sans commentaires."
)

_DEEPDIVE_SYSTEM = (
    "Tu es un expert en veille technologique. "
    "Tu approfondis un sujet via des recherches web complémentaires "
    "et produis une analyse enrichie en français."
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
        >>> si.deepdive
        ''
    """

    item: RawItem
    relevance: float
    summary_fr: str
    poc_idea: str
    tags: list[str] = field(default_factory=list)
    why_relevant: str = ""
    deepdive: str = ""


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
        "Articles à analyser :\n"
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


def _strip_fences(text: str) -> str:
    """Retire les fences Markdown (```json … ```) d'une réponse Claude.

    Args:
        text: Texte brut retourné par Claude.

    Returns:
        Texte nettoyé.

    Examples:
        >>> _strip_fences("```json\\n[1,2]\\n```")
        '[1,2]'
        >>> _strip_fences("[1,2]")
        '[1,2]'
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()
    return stripped


def analyze_batch(
    items: list[RawItem],
    profile: UserProfile,
    fulltext: dict[str, str],
    model: str = "claude-sonnet-4-20250514",
) -> list[ScoredItem]:
    """Analyse un batch d'articles via l'API Claude.

    Traite jusqu'à 20 items en un seul appel pour maîtriser les coûts.
    Le JSON retourné par Claude est parsé et converti en :class:`ScoredItem`.

    **Format de sortie attendu de Claude** ::

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

    articles_payload: list[dict[str, Any]] = [
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

    raw_text = _strip_fences(cast(TextBlock, response.content[0]).text)

    if not raw_text:
        logging.warning("analyze_batch: réponse Claude vide — batch ignoré.")
        return []

    try:
        results_raw: list[dict[str, Any]] = json.loads(raw_text)
    except json.JSONDecodeError:
        logging.warning(
            "analyze_batch: JSON invalide — batch ignoré.\n%s",
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


def deepdive(
    item: ScoredItem,
    profile: UserProfile,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Approfondit un article via l'outil de recherche web intégré à Claude.

    Utilisé automatiquement pour les articles dont ``relevance >= 9``.
    Claude effectue des recherches web complémentaires (via l'outil
    ``web_search`` du SDK Anthropic) et produit une analyse enrichie
    de 3 à 5 paragraphes en français.

    Args:
        item: Article à approfondir (doit avoir ``relevance >= 9``).
        profile: Profil utilisateur pour contextualiser l'analyse.
        model: Modèle Claude à utiliser.

    Returns:
        Analyse enrichie en Markdown, ou chaîne vide en cas d'erreur.

    Examples:
        >>> from veille_agent.bin.collector import RawItem
        >>> from veille_agent.bin.profile import UserProfile
        >>> raw = RawItem(title="t", url="https://x.com", source="s")
        >>> p = UserProfile(
        ...     topics=["dbt"],
        ...     context="Dev Python.",
        ...     scoring_high="h",
        ...     scoring_medium="m",
        ...     scoring_low="l",
        ...     threshold=6.0,
        ... )
        >>> si = ScoredItem(item=raw, relevance=9.0, summary_fr="ok", poc_idea="")
        >>> isinstance(deepdive.__doc__, str)
        True
    """
    prompt = (
        f"Contexte du développeur :\n{profile.context}\n\n"
        f'Article à approfondir : "{item.item.title}"\n'
        f"URL : {item.item.url}\n"
        f"Résumé initial : {item.summary_fr}\n\n"
        "Effectue des recherches web complémentaires sur ce sujet, "
        "puis rédige une analyse enrichie de 3 à 5 paragraphes en français. "
        "L'analyse doit couvrir :\n"
        "1. Les détails techniques importants non présents dans le résumé\n"
        "2. Le contexte dans l'écosystème (projets liés, alternatives)\n"
        "3. Les implications pratiques pour le développeur\n"
        "4. Des ressources complémentaires pertinentes\n\n"
        "Rédige directement l'analyse en Markdown (pas de JSON)."
    )

    try:
        response = _get_client().messages.create(
            model=model,
            max_tokens=2000,
            system=_DEEPDIVE_SYSTEM,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        # Récupérer uniquement les blocs de type "text" (ignorer tool_use/tool_result)
        text_blocks = [block.text for block in response.content if block.type == "text"]
        return "\n\n".join(text_blocks).strip()

    except anthropic.APIError as exc:
        logging.warning(
            "deepdive: erreur API Claude pour '%s' : %s", item.item.title, exc
        )
        return ""


def run_deepdives(
    scored_items: list[ScoredItem],
    profile: UserProfile,
    model: str = "claude-sonnet-4-20250514",
    threshold: float = 9.0,
) -> list[ScoredItem]:
    """Lance les deepdives pour les articles dépassant le seuil de pertinence.

    Args:
        scored_items: Tous les articles scorés de la semaine.
        profile: Profil utilisateur.
        model: Modèle Claude à utiliser.
        threshold: Score minimum pour déclencher un deepdive (défaut : 9.0).

    Returns:
        La même liste avec le champ ``deepdive`` renseigné pour les
        articles concernés.

    Examples:
        >>> from veille_agent.bin.profile import UserProfile
        >>> p = UserProfile(
        ...     topics=["dbt"],
        ...     context="Dev Python.",
        ...     scoring_high="h",
        ...     scoring_medium="m",
        ...     scoring_low="l",
        ...     threshold=6.0,
        ... )
        >>> run_deepdives([], p)
        []
    """
    candidates = [s for s in scored_items if s.relevance >= threshold]
    if not candidates:
        return scored_items

    print(f"    Deepdive sur {len(candidates)} article(s) score >= {threshold}...")
    for scored in candidates:
        print(f"      → {scored.item.title[:60]}...")
        scored.deepdive = deepdive(scored, profile, model=model)

    return scored_items
