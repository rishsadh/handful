#!/usr/bin/env python
"""Launch the local Streamlit demo.

Local only. Public deployment is not authorised by the specification: data
redistribution rights and access control must be settled first. See D-019 in
docs/DECISION_LOG.md.

Two things this handles that a bare `streamlit run` does not:

* **The first-run email prompt.** On a machine that has never run Streamlit, it stops at an
  interactive "Email:" prompt and the server never starts. Running headless skips it. That
  prompt appearing for the first time during a presentation is exactly the failure this
  avoids.
* **Opening the browser.** Headless mode does not, so this does it, after confirming the
  server is actually answering rather than guessing at a delay.

`--data-root` points the demo at a different project directory, which is how the synthetic
fixture is rehearsed before the real data exists. Any workspace whose provenance carries
the synthetic marker makes the demo show a permanent warning banner on every screen.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _wait_then_open(url: str, timeout: float = 90.0) -> None:
    """Open a browser once the server actually answers."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                print(f"\n  Demo ready at {url}\n")
                webbrowser.open(url)
                return
        except Exception:
            time.sleep(0.75)
    print(f"\n  Server did not answer within {timeout:.0f}s. Open {url} manually.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument(
        "--data-root",
        default=None,
        help="use a different project directory (e.g. a synthetic smoke workspace)",
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    try:
        import streamlit  # noqa: F401
    except ImportError:
        print(
            "streamlit is not installed. Run:  python tasks.py setup\n"
            "(or: pip install -e '.[app]')",
            file=sys.stderr,
        )
        return 1

    env = dict(os.environ)
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    if args.data_root:
        root = Path(args.data_root).resolve()
        if not (root / "config").is_dir():
            print(f"--data-root {root} has no config/ directory", file=sys.stderr)
            return 1
        env["FOODCOM_PROJECT_ROOT"] = str(root)
        print(f"data root: {root}")

    url = f"http://localhost:{args.port}"
    app = ROOT / "app" / "streamlit_app.py"
    print(f"launching {app}")
    print(f"  {url}   (press Ctrl+C to stop)")

    if not args.no_browser:
        threading.Thread(target=_wait_then_open, args=(url,), daemon=True).start()

    return subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", str(app),
            # Headless skips Streamlit's first-run email prompt, which otherwise blocks
            # startup forever on a fresh machine. The browser is opened above instead.
            "--server.headless", "true",
            "--server.port", str(args.port),
            "--browser.gatherUsageStats", "false",
        ],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
