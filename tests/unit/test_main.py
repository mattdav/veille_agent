"""Tests pour __main__.py."""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytest import MonkeyPatch

from veille_agent import __main__ as main_module
from veille_agent.bin.analyst import ScoredItem
from veille_agent.bin.collector import RawItem
from veille_agent.bin.profile import UserProfile


def _profile(**overrides: object) -> UserProfile:
    base: dict[str, object] = {
        "topics": ["dbt"],
        "context": "c",
        "scoring_high": "h",
        "scoring_medium": "m",
        "scoring_low": "l",
        "threshold": 6.0,
        "rss_feeds": [{"name": "Src", "url": "https://x.com/feed"}],
        "arxiv_categories": [],
        "github_topics": [],
        "youtube_channels": [],
    }
    base.update(overrides)
    return UserProfile(**base)  # type: ignore[arg-type]


def test_get_package_dir_returns_existing_folder() -> None:
    """Le dossier retourné doit exister (créé s'il ne l'était pas déjà)."""
    path = main_module._get_package_dir("data")
    assert path.exists()
    assert path.is_dir()


def test_setup_logging_creates_log_file(tmp_path: Path) -> None:
    """_setup_logging doit créer log/app.log sans laisser de handler orphelin."""
    root = logging.getLogger()
    before = list(root.handlers)
    log_path = tmp_path / "log"
    try:
        main_module._setup_logging(log_path)
        assert (log_path / "app.log").exists()
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)


def test_run_dry_run_returns_empty(tmp_path: Path) -> None:
    """En dry-run, aucun appel Claude n'est fait et le résultat est vide."""
    profile = _profile(rss_feeds=[], arxiv_categories=[], github_topics=[])
    result = main_module.run(
        profile=profile,
        db_path=str(tmp_path / "watch.db"),
        output_dir=tmp_path / "briefings",
        dry_run=True,
    )
    assert result == []


def test_run_full_pipeline_with_deepdive_and_email(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Le pipeline complet doit persister, deepdiver, publier et envoyer l'email."""
    monkeypatch.setenv("CLAUDE_MODEL_BATCH", "claude-haiku-4-5")
    monkeypatch.setenv("CLAUDE_MODEL_DEEPDIVE", "claude-sonnet-5")

    raw = RawItem(
        title="dbt core update",
        url="https://x.com/a",
        source="Src",
        summary="Court résumé dbt.",
    )
    scored = ScoredItem(
        item=raw, relevance=9.5, summary_fr="ok", poc_idea="", tags=["dbt"]
    )

    with (
        patch.object(main_module, "collect_rss", return_value=[raw]),
        patch.object(main_module, "fetch_fulltext", return_value=""),
        patch.object(main_module, "analyze_batch", return_value=[scored]),
        patch.object(
            main_module, "run_deepdives", return_value=[scored]
        ) as mocked_deepdives,
        patch.object(
            main_module, "generate_html_briefing", return_value="<html></html>"
        ),
        patch.object(main_module, "generate_markdown_briefing", return_value="# md"),
        patch.object(main_module, "send_email") as mocked_send_email,
        patch.object(main_module, "publish_briefing") as mocked_publish,
    ):
        result = main_module.run(
            profile=_profile(),
            db_path=str(tmp_path / "watch.db"),
            output_dir=tmp_path / "briefings",
            email_to="dest@example.com",
            publish_path=str(tmp_path / "publish"),
            enable_deepdive=True,
        )

    assert result == [scored]
    mocked_deepdives.assert_called_once()
    mocked_send_email.assert_called_once()
    mocked_publish.assert_called_once()
    assert (tmp_path / "briefings").exists()


def test_run_full_pipeline_without_deepdive_or_email(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Sans deepdive ni email, ces étapes doivent être ignorées proprement."""
    monkeypatch.setenv("CLAUDE_MODEL_BATCH", "claude-haiku-4-5")

    raw = RawItem(
        title="dbt core update",
        url="https://x.com/b",
        source="Src",
        summary="Court résumé dbt.",
    )
    scored = ScoredItem(
        item=raw, relevance=7.0, summary_fr="ok", poc_idea="", tags=["dbt"]
    )

    with (
        patch.object(main_module, "collect_rss", return_value=[raw]),
        patch.object(main_module, "fetch_fulltext", return_value=""),
        patch.object(main_module, "analyze_batch", return_value=[scored]),
        patch.object(main_module, "run_deepdives") as mocked_deepdives,
        patch.object(
            main_module, "generate_html_briefing", return_value="<html></html>"
        ),
        patch.object(main_module, "generate_markdown_briefing", return_value="# md"),
    ):
        result = main_module.run(
            profile=_profile(),
            db_path=str(tmp_path / "watch.db"),
            output_dir=tmp_path / "briefings",
            enable_deepdive=False,
        )

    assert result == [scored]
    mocked_deepdives.assert_not_called()


def test_main_dispatches_recap(monkeypatch: MonkeyPatch) -> None:
    """--recap doit appeler generate_monthly_recap et jamais run."""
    monkeypatch.setattr(sys, "argv", ["veille_agent", "--recap"])
    monkeypatch.setattr(main_module, "_setup_logging", lambda *_: None)
    monkeypatch.setattr(main_module, "load_profile", lambda *_: _profile())
    fake_recap = MagicMock(return_value=[])
    fake_run = MagicMock()
    monkeypatch.setattr(main_module, "generate_monthly_recap", fake_recap)
    monkeypatch.setattr(main_module, "run", fake_run)

    main_module.main()

    fake_recap.assert_called_once()
    fake_run.assert_not_called()


def test_main_dispatches_run_with_cli_flags(monkeypatch: MonkeyPatch) -> None:
    """Les flags CLI doivent être répercutés dans les kwargs passés à run."""
    monkeypatch.setattr(
        sys, "argv", ["veille_agent", "--dry-run", "--no-youtube", "--no-deepdive"]
    )
    monkeypatch.setattr(main_module, "_setup_logging", lambda *_: None)
    monkeypatch.setattr(main_module, "load_profile", lambda *_: _profile())
    fake_run = MagicMock(return_value=[])
    monkeypatch.setattr(main_module, "run", fake_run)

    main_module.main()

    fake_run.assert_called_once()
    _, kwargs = fake_run.call_args
    assert kwargs["dry_run"] is True
    assert kwargs["enable_youtube"] is False
    assert kwargs["enable_deepdive"] is False


def test_main_handles_exception_and_exits(monkeypatch: MonkeyPatch) -> None:
    """Une exception dans run() doit être logguée et provoquer sys.exit(1)."""
    monkeypatch.setattr(sys, "argv", ["veille_agent"])
    monkeypatch.setattr(main_module, "_setup_logging", lambda *_: None)
    monkeypatch.setattr(main_module, "load_profile", lambda *_: _profile())

    def _boom(**_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "run", _boom)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()
    assert exc_info.value.code == 1
