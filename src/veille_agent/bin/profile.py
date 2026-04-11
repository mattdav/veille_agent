"""Chargement du profil utilisateur depuis le fichier YAML déclaratif."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class UserProfile:
    """Profil utilisateur chargé depuis ``config/profile.yaml``.

    Encapsule les thématiques, le contexte narratif et les critères de
    scoring injectés dans le prompt Claude.

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
    )
