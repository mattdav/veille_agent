"""Tâches d'automatisation du projet via invoke.

Usage::

    inv lint        # ruff check + ruff format --check + mypy
    inv format      # ruff format (correction en place)
    inv test        # pytest (doctest + unitaires + coverage)
    inv check       # lint + test (CI complète)
    inv run         # python -m veille_agent
    inv dry-run     # python -m veille_agent --dry-run
    inv recap       # recap mensuel Top-K
"""

from invoke import Context, task  # type: ignore[import-untyped]

SRC = "src/veille_agent"
TESTS = "tests"
ALL_PATHS = f"{SRC} {TESTS} tasks.py"


@task
def format(ctx: Context) -> None:
    """Formate le code avec ruff format."""
    ctx.run(f"ruff format {ALL_PATHS}", pty=False)


@task
def lint(ctx: Context) -> None:
    """Vérifie le style (ruff), le formatage (ruff format) et les types (mypy).

    Retourne un code d'erreur non nul si l'une des vérifications échoue.
    """
    ctx.run(f"ruff check {ALL_PATHS}", pty=False)
    ctx.run(f"ruff format --check {ALL_PATHS}", pty=False)
    ctx.run(f"mypy {SRC}", pty=False)


@task
def test(ctx: Context) -> None:
    """Lance la suite de tests pytest (doctest + unitaires + coverage)."""
    ctx.run("pytest", pty=False)


@task
def check(ctx: Context) -> None:
    """Pipeline CI complète : lint puis tests."""
    lint(ctx)
    test(ctx)


@task
def run(ctx: Context, email: str = "", output_dir: str = "", no_youtube: bool = False, no_deepdive: bool = False) -> None:
    """Lance l'agent de veille hebdomadaire complet.

    Args:
        email: Adresse email destinataire du briefing (optionnel).
        output_dir: Dossier de sortie des briefings (optionnel).
        no_youtube: Désactiver la collecte YouTube.
        no_deepdive: Désactiver le deepdive automatique.
    """
    cmd = "python -m veille_agent"
    if email:
        cmd += f" --email {email}"
    if output_dir:
        cmd += f" --output-dir {output_dir}"
    if no_youtube:
        cmd += " --no-youtube"
    if no_deepdive:
        cmd += " --no-deepdive"
    ctx.run(cmd, pty=False)


@task(name="dry-run")
def dry_run(ctx: Context) -> None:
    """Lance l'agent en mode dry-run (collecte + filtre, sans Claude)."""
    ctx.run("python -m veille_agent --dry-run", pty=False)


@task
def recap(ctx: Context, email: str = "", weeks: int = 0) -> None:
    """Génère le recap mensuel Top-K des tendances structurantes.

    Args:
        email: Adresse email destinataire du recap (optionnel).
        weeks: Fenêtre en semaines (0 = valeur par défaut du config).
    """
    cmd = "python -m veille_agent --recap"
    if email:
        cmd += f" --email {email}"
    if weeks:
        cmd += f" --recap-weeks {weeks}"
    ctx.run(cmd, pty=False)
