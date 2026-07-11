import shutil
import subprocess
from pathlib import Path

from invoke import Context, task

# ================ Config ================= #
CLEAN_DIRS: list[str] = [
    "build",  # Build artefacts
    "dist",  # Packaged distributions
    ".pytest_cache",  # pytest cache
    ".ruff_cache",  # Ruff cache
    ".mypy_cache",  # mypy cache
    ".okflint",  # JSON audit reports (regeneratable)
    "htmlcov",  # HTML coverage report
    "__pycache__",  # Python cache (root)
]

CLEAN_FILES: list[str] = [
    ".coverage",  # pytest-cov coverage data
]


# ================ Helper Functions ================= #
@task
def clean(c: Context) -> None:
    """Remove build artifacts and caches."""
    for directory in CLEAN_DIRS:
        path: Path = Path(directory)
        if path.exists():
            print(f"  - Removing {directory}")
            shutil.rmtree(path, ignore_errors=True)

    for filename in CLEAN_FILES:
        path = Path(filename)
        if path.exists():
            print(f"  - Removing {filename}")
            path.unlink(missing_ok=True)

    # Recursively clean __pycache__
    for path in Path(".").rglob("__pycache__"):
        print(f"  - Removing {path}")
        shutil.rmtree(path, ignore_errors=True)

    # Clean *.egg-info
    for path in Path(".").rglob("*.egg-info"):
        print(f"  - Removing {path}")
        shutil.rmtree(path, ignore_errors=True)

    # Clean .pyc files
    for path in Path(".").rglob("*.pyc"):
        print(f"  - Removing {path}")
        path.unlink(missing_ok=True)

    print("🗑 Clean task Done!")


# ================ Quality test ================= #
@task
def index(c: Context) -> None:
    """Index the codebase in codebase-memory-mcp to improve Claude Code context.

    Uses the CLI mode of the codebase-memory-mcp binary to index the current
    project into the persistent knowledge graph. The index survives session
    restarts and allows Claude Code to make structural queries
    (call graph, dependencies, etc.) with ~99% fewer tokens than a file-by-file
    exploration.

    Re-run after every significant change to the codebase.
    """
    import json

    binary = Path(
        r"C:\Users\matth\AppData\Local\Programs\codebase-memory-mcp\codebase-memory-mcp.exe"
    )
    if not binary.exists():
        print(f"❌ codebase-memory-mcp binary not found: {binary}")
        print("   Install from: https://github.com/DeusData/codebase-memory-mcp")
        return

    repo_path = str(Path.cwd()).replace("\\", "/")
    payload = json.dumps({"repo_path": repo_path})

    print("🧠 Indexing codebase in codebase-memory-mcp...")
    print(f"   Project: {repo_path}")
    result = subprocess.run(
        [str(binary), "cli", "index_repository", payload],
        shell=False,
    )
    if result.returncode == 0:
        print("✅ Index updated. Claude Code can now query the knowledge graph.")
    else:
        print("❌ Indexing failed.")


@task
def lint(c: Context) -> None:
    """Run linting checks."""
    result = 0
    print("Running Ruff check...")
    check_command = subprocess.run("uv run ruff check --fix src/.", shell=True)
    if check_command.returncode != 0:
        result += check_command.returncode
    print("\nRunning Ruff format check...")
    format_command = subprocess.run("uv run ruff format src/.", shell=True)
    if format_command.returncode != 0:
        result += format_command.returncode
    print("\nRunning mypy...")
    # uv run mypy fails on Windows with compiled mypy (Failed to canonicalize script path)
    # Using python -m mypy as a workaround
    mypy_command = subprocess.run("uv run python -m mypy src/.", shell=True)
    if mypy_command.returncode != 0:
        result += mypy_command.returncode
    if result != 0:
        print("❌ Linting issues found!")
    else:
        print("🔎 Linting Task Done!")


@task
def test(c: Context, verbose: bool = False, coverage: bool = True) -> None:
    """Run the pytest test suite."""
    print("🧪 Running test suite...")

    # Build the command
    cmd = "uv run python -m pytest"
    if verbose:
        cmd += " -v"
    if not coverage:
        # pyproject.toml enables coverage by default via addopts
        cmd += " --no-cov"

    # Execute
    result = subprocess.run(cmd, shell=True)

    if result.returncode != 0:
        print("❌ Tests failed!")
    else:
        print("✅ All tests passed!")
        html_report = Path("htmlcov") / "index.html"
        if html_report.exists():
            print(f"📊 HTML report: {html_report.resolve()}")


@task
def docs(c: Context, open_browser: bool = False) -> None:
    """Build the Sphinx documentation as HTML."""
    src = Path("docs/source")
    out = src / "_build" / "html"
    out.mkdir(parents=True, exist_ok=True)

    print("📖 Building Sphinx documentation...")
    result = subprocess.run(
        f'uv run sphinx-build -b html "{src}" "{out}"',
        shell=True,
    )
    if result.returncode != 0:
        print("❌ Sphinx build failed!")
        return

    index_html = out / "index.html"
    print(f"✅ Documentation built: {index_html.resolve()}")

    # Optionally open in browser
    if open_browser:
        import webbrowser

        webbrowser.open(index_html.as_uri())
