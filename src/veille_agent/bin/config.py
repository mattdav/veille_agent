"""Configuration centrale de l'agent de veille."""

from dataclasses import dataclass, field


@dataclass
class WatchConfig:
    """Paramètres de personnalisation de l'agent de veille.

    Tous les réglages métier sont centralisés ici.
    Les valeurs par défaut correspondent au profil data-engineering / IA.

    Examples:
        >>> cfg = WatchConfig()
        >>> "dbt" in cfg.topics
        True
        >>> cfg.min_relevance_score
        6.0
    """

    # Thématiques filtrantes — adaptez à vos centres d'intérêt
    topics: list[str] = field(
        default_factory=lambda: [
            "dbt",
            "data engineering",
            "python",
            "LLM",
            "agents IA",
            "pydantic",
            "polars",
            "cookiecutter",
            "RAG",
            "MCP",
        ]
    )

    rss_feeds: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"name": "Hacker News Best", "url": "https://hnrss.org/best"},
            {
                "name": "Towards Data Science",
                "url": "https://towardsdatascience.com/feed",
            },
            {
                "name": "The Batch (deepl.)",
                "url": "https://www.deeplearning.ai/the-batch/feed/",
            },
            {"name": "dbt blog", "url": "https://www.getdbt.com/blog/rss.xml"},
            {"name": "Martin Fowler", "url": "https://martinfowler.com/feed.atom"},
            {"name": "Anthropic news", "url": "https://www.anthropic.com/rss.xml"},
        ]
    )

    arxiv_categories: list[str] = field(
        default_factory=lambda: ["cs.AI", "cs.LG", "cs.SE"]
    )

    github_topics: list[str] = field(
        default_factory=lambda: ["llm", "data-engineering", "python", "agents"]
    )

    # Score minimum pour apparaître dans le briefing (0-10)
    min_relevance_score: float = 6.0
    max_items_per_briefing: int = 20

    # Nombre de jours en arrière pour la collecte RSS
    rss_since_days: int = 7

    # Taille des batches envoyés à Claude
    claude_batch_size: int = 20

    # Modèle Claude à utiliser
    claude_model: str = "claude-sonnet-4-20250514"
