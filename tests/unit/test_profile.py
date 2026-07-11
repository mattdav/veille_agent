"""Tests pour bin/profile.py."""

from pathlib import Path

import pytest

from veille_agent.bin.profile import load_profile


def test_load_profile_missing_file_raises(tmp_path: Path) -> None:
    """Un fichier profil absent doit lever FileNotFoundError."""
    missing = tmp_path / "absent.yaml"
    with pytest.raises(FileNotFoundError):
        load_profile(missing)
