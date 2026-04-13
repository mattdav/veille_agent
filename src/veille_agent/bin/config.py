"""Configuration centrale de l'agent de veille."""

from dataclasses import dataclass, field


@dataclass
class WatchConfig:
    """Paramètres techniques de l'agent de veille.

    Centralisés ici : sources, seuils, modèle, comportement des nouvelles
    fonctionnalités (YouTube, deepdive, recap mensuel).

    Examples:
        >>> cfg = WatchConfig()
        >>> cfg.min_relevance_score
        6.0
        >>> cfg.deepdive_threshold
        9.0
        >>> cfg.recap_since_weeks
        4
    """

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

    # Chaînes YouTube à surveiller — identifiants UC... ou handles @NomChaine
    youtube_channels: list[str] = field(
        default_factory=lambda: [
            "@dbt-labs",
            "@PyCon",
            "UCCTVrRjpphcfzTb9vCuhHsA",  # Andrej Karpathy
        ]
    )

    # Nombre max de vidéos par chaîne YouTube par run
    youtube_max_per_channel: int = 3

    # Score minimum pour apparaître dans le briefing (0-10)
    min_relevance_score: float = 6.0
    max_items_per_briefing: int = 20

    # Score minimum pour déclencher un deepdive automatique (0-10)
    deepdive_threshold: float = 9.0

    # Nombre de jours en arrière pour la collecte RSS et YouTube
    rss_since_days: int = 7

    # Taille des batches envoyés à Claude pour l'analyse
    claude_batch_size: int = 20

    # Modèle Claude à utiliser pour toutes les fonctions IA
    claude_model: str = "claude-sonnet-4-20250514"

    # Fenêtre du recap mensuel en semaines
    recap_since_weeks: int = 4
