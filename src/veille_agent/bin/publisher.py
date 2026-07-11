"""Publication du briefing markdown vers un répertoire secondaire (ex : vault Obsidian)."""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def publish_briefing(md_path: Path, publish_path: str) -> None:
    """Copie le briefing markdown vers un répertoire secondaire.

    Canal secondaire par rapport à ``output_dir`` (sauvegarde principale) et
    à l'email : toute erreur (répertoire inexistant, permissions) est loggée
    en warning sans remonter d'exception, pour ne pas faire échouer le run.

    Args:
        md_path: Chemin du fichier markdown déjà écrit dans ``output_dir``.
        publish_path: Répertoire de destination (ex : point de montage vers
            un vault Obsidian synchronisé).

    Examples:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as src_dir, \\
        ...      tempfile.TemporaryDirectory() as dst_dir:
        ...     src = Path(src_dir) / "2025-W42.md"
        ...     _ = src.write_text("# Briefing", encoding="utf-8")
        ...     publish_briefing(src, dst_dir)
        ...     (Path(dst_dir) / "2025-W42.md").read_text(encoding="utf-8")
        '# Briefing'
        >>> with tempfile.TemporaryDirectory() as src_dir:
        ...     src = Path(src_dir) / "2025-W42.md"
        ...     _ = src.write_text("# Briefing", encoding="utf-8")
        ...     publish_briefing(src, "/chemin/totalement/inexistant")
    """
    dest = Path(publish_path) / md_path.name
    try:
        shutil.copy2(md_path, dest)
    except OSError as exc:
        logger.warning("Échec de la copie du briefing vers %s : %s", publish_path, exc)
        return
    logger.info("Briefing copié vers %s", dest)
