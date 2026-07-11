"""Chargement du profil utilisateur depuis le fichier YAML déclaratif."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class UserProfile:
    """Profil utilisateur chargé depuis ``config/profile.yaml``.

    Porte tout ce qui est personnalisable dans l'agent : thématiques,
    contexte narratif, critères de scoring, sources à surveiller et
    paramètres techniques (modèle Claude, seuils, tailles de batch).

    Examples:
        >>> p = UserProfile(
        ...     topics=["dbt", "python"],
        ...     context="Dev Python senior.",
        ...     scoring_high="utilisable cette semaine",
        ...     scoring_medium="applicable à moyen terme",
        ...     scoring_low="trop éloigné",
        ...     threshold=6.0,
        ... )
        >>> "dbt" in p.topics
        True
        >>> p.threshold
        6.0
    """

    topics: list[str]
    context: str
    scoring_high: str
    scoring_medium: str
    scoring_low: str
    threshold: float
    rss_feeds: list[dict[str, str]] = field(default_factory=list)
    arxiv_categories: list[str] = field(default_factory=list)
    github_topics: list[str] = field(default_factory=list)
    youtube_channels: list[str] = field(default_factory=list)
    youtube_max_per_channel: int = 3
    max_items_per_briefing: int = 20
    deepdive_threshold: float = 9.0
    rss_since_days: int = 7
    claude_batch_size: int = 20
    recap_since_weeks: int = 4


def load_profile(path: Path) -> UserProfile:
    """Charge le profil utilisateur depuis un fichier YAML.

    Args:
        path: Chemin vers le fichier ``profile.yaml``.

    Returns:
        Instance de :class:`UserProfile`.

    Raises:
        FileNotFoundError: Si le fichier n'existe pas.
        KeyError: Si une clé obligatoire est absente du YAML.

    Examples:
        >>> import tempfile, pathlib, textwrap
        >>> yaml_content = textwrap.dedent('''
        ...     topics: [dbt, python]
        ...     context: "Dev Python."
        ...     scoring:
        ...       high: "utilisable"
        ...       medium: "moyen terme"
        ...       low: "eloigne"
        ...       threshold: 6.0
        ...     rss_feeds:
        ...       - name: "Hacker News Best"
        ...         url: "https://hnrss.org/best"
        ...     arxiv_categories: [cs.AI, cs.LG]
        ...     github_topics: [llm, python]
        ...     youtube_channels: ["@PyCon"]
        ...     youtube_max_per_channel: 3
        ...     max_items_per_briefing: 20
        ...     deepdive_threshold: 9.0
        ...     rss_since_days: 7
        ...     claude_batch_size: 20
        ...     recap_since_weeks: 4
        ... ''')
        >>> with tempfile.NamedTemporaryFile(
        ...     mode='w', suffix='.yaml', delete=False, encoding='utf-8'
        ... ) as f:
        ...     _ = f.write(yaml_content)
        ...     tmp = pathlib.Path(f.name)
        >>> profile = load_profile(tmp)
        >>> profile.topics
        ['dbt', 'python']
        >>> profile.threshold
        6.0
        >>> profile.rss_feeds[0]["name"]
        'Hacker News Best'
        >>> tmp.unlink()
    """
    if not path.exists():
        raise FileNotFoundError(f"Profil introuvable : {path}")

    with path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)

    scoring = data["scoring"]
    return UserProfile(
        topics=data["topics"],
        context=data["context"].strip(),
        scoring_high=scoring["high"],
        scoring_medium=scoring["medium"],
        scoring_low=scoring["low"],
        threshold=float(scoring["threshold"]),
        rss_feeds=data["rss_feeds"],
        arxiv_categories=data["arxiv_categories"],
        github_topics=data["github_topics"],
        youtube_channels=data["youtube_channels"],
        youtube_max_per_channel=int(data["youtube_max_per_channel"]),
        max_items_per_briefing=int(data["max_items_per_briefing"]),
        deepdive_threshold=float(data["deepdive_threshold"]),
        rss_since_days=int(data["rss_since_days"]),
        claude_batch_size=int(data["claude_batch_size"]),
        recap_since_weeks=int(data["recap_since_weeks"]),
    )
