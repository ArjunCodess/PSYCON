"""Load local deployment secrets without overriding explicit process settings."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_environment(
    path: str | Path | None = None, *, override: bool = False
) -> bool:
    """Load the repository .env file before runtime services read configuration."""

    environment_path = Path(path) if path is not None else PROJECT_ROOT / ".env"
    return load_dotenv(environment_path, override=override)
