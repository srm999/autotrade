"""Helpers for loading Schwab credentials from a .env-style file."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from autotrade.config import SchwabCredentials

_ENV_KEYS: set[str] = {
    "SCHWAB_APP_KEY",
    "SCHWAB_APP_SECRET",
    "SCHWAB_ACCOUNT_NUMBER",
    "SCHWAB_ACCOUNT_HASH",
    "SCHWAB_TOKEN_PATH",
    "SCHWAB_CALLBACK_URL",
}


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from a .env file into a dict."""
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise ValueError(f"Invalid line {line_number} in {path}: {raw_line!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Missing key on line {line_number} in {path}")
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _candidate_paths(dotenv_path: str | os.PathLike[str]) -> Iterable[Path]:
    """Yield plausible locations for the dotenv file."""
    explicit = Path(dotenv_path).expanduser()
    yield explicit
    if explicit.is_absolute():
        return
    project_root = Path(__file__).resolve().parents[2]
    yield project_root / explicit


def get_schwab_credentials(
    dotenv_path: str | os.PathLike[str] = ".env",
    *,
    override: bool = False,
) -> SchwabCredentials:
    """Load Schwab credentials from the environment, optionally hydrating from a .env file."""
    explicit_path = os.getenv("SCHWAB_DOTENV_PATH") or dotenv_path
    for candidate in _candidate_paths(explicit_path):
        if not candidate.exists():
            continue
        entries = _parse_dotenv(candidate)
        for key in _ENV_KEYS:
            if key in entries and (override or os.getenv(key) is None):
                os.environ[key] = entries[key]
        break
    return SchwabCredentials.from_env()
