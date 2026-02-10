#!/usr/bin/env python3
"""Interactive helper for creating the Schwab OAuth token file."""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from schwab import auth

from autotrade.utils.env_loader import get_schwab_credentials


def _default_webdriver():
    """Return a Selenium webdriver suitable for the Schwab login flow."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:  # pragma: no cover - requires selenium installed
        raise SystemExit(
            "Install selenium and a compatible browser driver (e.g., Chrome + chromedriver) before running this script."
        ) from exc

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1200,900")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    return webdriver.Chrome(options=chrome_options)


def main() -> None:
    credentials = get_schwab_credentials()
    callback_url = os.getenv("SCHWAB_CALLBACK_URL", "").strip()
    if not callback_url:
        raise SystemExit("Set SCHWAB_CALLBACK_URL to your Schwab app redirect URL before running this script.")
    token_path = Path(credentials.token_path).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Launching Schwab login flow to create {token_path} ...")
    kwargs = {}
    if "webdriver_func" in inspect.signature(auth.easy_client).parameters:
        kwargs["webdriver_func"] = _default_webdriver
    auth.easy_client(
        credentials.app_key,
        credentials.app_secret,
        callback_url,
        str(token_path),
        **kwargs,
    )
    print(f"Token saved to {token_path}")


if __name__ == "__main__":
    main()
