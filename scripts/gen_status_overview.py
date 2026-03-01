#!/usr/bin/env python3
"""Generate a small status snapshot for docs.

Purpose:
- Reduce manual doc drift by deriving status from the repo at runtime.

What it prints:
- current date (UTC)
- git commit SHA (short)
- `pytest -q` summary line (counts)

Usage:
  python scripts/gen_status_overview.py

Note:
- This script runs pytest, so it may take some seconds.
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
from typing import Optional


def _run(cmd: list[str], *, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def main() -> int:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    sha = "unknown"
    p = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
    if p.returncode == 0:
        sha = (p.stdout or "").strip()

    p = _run([sys.executable, "-m", "pytest", "-q"], cwd=repo_root)
    if p.returncode != 0:
        sys.stdout.write(p.stdout)
        return p.returncode

    # pytest -q last line is usually the summary; keep it robust.
    lines = [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]
    summary = lines[-1] if lines else "(no pytest output)"

    md = (
        "## Status snapshot\n\n"
        f"- Date (UTC): `{now}`\n"
        f"- Git: `{sha}`\n"
        f"- Tests: `{summary}`\n"
    )
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
