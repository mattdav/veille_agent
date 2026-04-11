"""Pré-filtrage thématique par mots-clés avant analyse Claude."""

import re

from veille_agent.bin.collector import RawItem


def keyword_score(item: RawItem, topics: list[str]) -> float:
    """Calcule un score de pertinence 0-1 par correspondance de mots-clés.

    Args:
        item: Article à scorer.
        topics: Liste de thématiques de référence.

    Returns:
        Score entre 0.0 et 1.0.

    Examples:
        >>> from veille_agent.bin.collector import RawItem
        >>> item = RawItem(title="dbt core update", url="https://x.com", source="RSS")
        >>> keyword_score(item, ["dbt", "python"]) > 0
        True
        >>> keyword_score(item, []) == 0.0
        True
    """
    if not topics:
        return 0.0
    text = (item.title + " " + item.summary).lower()
    hits = sum(
        1 for t in topics if re.search(r"\b" + re.escape(t.lower()) + r"\b", text)
    )
    return min(hits / max(len(topics) * 0.3, 1), 1.0)


def pre_filter(
    items: list[RawItem],
    topics: list[str],
    threshold: float = 0.08,
) -> list[RawItem]:
    """Élimine les items clairement hors-sujet avant l'analyse Claude.

    Le seuil est volontairement bas (0.08) pour ne pas rater de signal —
    Claude affine le scoring ensuite.

    Args:
        items: Articles à filtrer.
        topics: Thématiques de référence.
        threshold: Score minimum pour conserver un item.

    Returns:
        Sous-liste des items dont le score dépasse le seuil.

    Examples:
        >>> pre_filter([], ["dbt"])
        []
    """
    return [item for item in items if keyword_score(item, topics) >= threshold]
