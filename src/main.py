"""Main launcher for Game Leaderboard Analyzer local Web UI."""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn

from src.config import DEFAULT_HOST, DEFAULT_PORT, ensure_base_dirs


def _open_browser_delayed(url: str, delay_sec: float = 1.2) -> None:
    time.sleep(delay_sec)
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Game Leaderboard Analyzer Local Web UI")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")
    args = parser.parse_args()

    ensure_base_dirs()
    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Thread(target=_open_browser_delayed, args=(url,), daemon=True).start()

    uvicorn.run("src.web.api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
