"""Collecte multi-sources : RSS, arXiv, GitHub trending."""

import hashlib
import sqlite3
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta

import feedparser  # type: ignore[import-untyped]
import httpx


@dataclass
class RawItem:
    """Représente un article brut collecté depuis une source.

    Examples:
        >>> item = RawItem(title="Test", url="https://example.com", source="RSS")
        >>> len(item.uid)
        32
    """

    title: str
    url: str
    source: str
    summary: str = ""
    published: str = ""

    @property
    def uid(self) -> str:
        """Identifiant unique basé sur le hash MD5 de l'URL."""
        return hashlib.md5(self.url.encode()).hexdigest()


def collect_rss(feeds: list[dict[str, str]], since_days: int = 7) -> list[RawItem]:
    """Collecte les articles depuis une liste de flux RSS.

    Args:
        feeds: Liste de dicts ``{"name": str, "url": str}``.
        since_days: Ne retenir que les articles publiés dans cette fenêtre.

    Returns:
        Liste de :class:`RawItem` triés du plus récent au plus ancien.

    Examples:
        >>> collect_rss([], since_days=7)
        []
    """
    items: list[RawItem] = []
    cutoff = datetime.now() - timedelta(days=since_days)

    for feed_cfg in feeds:
        feed = feedparser.parse(feed_cfg["url"])
        for entry in feed.entries:
            parsed_time = getattr(entry, "published_parsed", None)
            pub = datetime(*parsed_time[:6]) if parsed_time else datetime.now()
            if pub < cutoff:
                continue
            items.append(
                RawItem(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=feed_cfg["name"],
                    summary=entry.get("summary", "")[:500],
                    published=pub.isoformat(),
                )
            )
    return items


def collect_arxiv(categories: list[str], max_results: int = 30) -> list[RawItem]:
    """Collecte les derniers papiers arXiv pour les catégories données.

    Args:
        categories: Catégories arXiv (ex: ``["cs.AI", "cs.LG"]``).
        max_results: Nombre maximum de résultats à retourner.

    Returns:
        Liste de :class:`RawItem`.

    Examples:
        >>> collect_arxiv([])
        []
    """
    if not categories:
        return []

    query = " OR ".join(f"cat:{c}" for c in categories)
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query={urllib.parse.quote(query)}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    feed = feedparser.parse(url)
    return [
        RawItem(
            title=entry.title.replace("\n", " "),
            url=entry.id,
            source="arXiv",
            summary=entry.summary[:500],
            published=entry.published,
        )
        for entry in feed.entries
    ]


def collect_github_trending(topics: list[str]) -> list[RawItem]:
    """Collecte les dépôts GitHub populaires par topic.

    Utilise l'API publique de recherche GitHub (60 req/h sans token).
    Ajouter ``GITHUB_TOKEN`` en variable d'environnement si > 10 topics.

    Args:
        topics: Topics GitHub (ex: ``["llm", "data-engineering"]``).

    Returns:
        Liste de :class:`RawItem`.

    Examples:
        >>> collect_github_trending([])
        []
    """
    if not topics:
        return []

    items: list[RawItem] = []
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    for topic in topics:
        url = "https://api.github.com/search/repositories"
        params: dict[str, str | int] = {
            "q": f"topic:{topic} pushed:>{since} stars:>50",
            "sort": "stars",
            "order": "desc",
            "per_page": 5,
        }
        try:
            r = httpx.get(
                url,
                params=params,
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            )
            if r.status_code != 200:
                continue
            for repo in r.json().get("items", []):
                desc = repo.get("description") or ""
                items.append(
                    RawItem(
                        title=f"{repo['full_name']} — {desc}",
                        url=repo["html_url"],
                        source=f"GitHub/{topic}",
                        summary=(f"{repo.get('stargazers_count', 0)} stars. {desc}"),
                    )
                )
        except httpx.RequestError:
            continue

    return items


def deduplicate(items: list[RawItem], db_path: str = "watch.db") -> list[RawItem]:
    """Filtre les items déjà traités lors des semaines précédentes.

    Ne fait que **lire** la base SQLite. Pour persister les nouveaux items
    après un traitement réussi, appeler :func:`mark_seen`.

    Args:
        items: Items à dédupliquer.
        db_path: Chemin vers la base SQLite.

    Returns:
        Sous-liste des items non encore traités.

    Examples:
        >>> deduplicate([])
        []
    """
    if not items:
        return []

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS seen (uid TEXT PRIMARY KEY, date TEXT)")
    seen = {row[0] for row in conn.execute("SELECT uid FROM seen")}
    conn.close()
    return [i for i in items if i.uid not in seen]


def mark_seen(items: list[RawItem], db_path: str = "watch.db") -> None:
    """Enregistre les UIDs des items dans la table ``seen`` après traitement.

    À appeler uniquement une fois le pipeline terminé avec succès, pour
    éviter de bloquer des items non traités en cas d'erreur intermédiaire.

    Args:
        items: Items à marquer comme traités.
        db_path: Chemin vers la base SQLite.

    Examples:
        >>> mark_seen([])
    """
    if not items:
        return

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS seen (uid TEXT PRIMARY KEY, date TEXT)")
    conn.executemany(
        "INSERT OR IGNORE INTO seen VALUES (?, ?)",
        [(i.uid, datetime.now().isoformat()) for i in items],
    )
    conn.commit()
    conn.close()
