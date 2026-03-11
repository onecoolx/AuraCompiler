from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_dump_tokens_only_to_writes_and_stops(tmp_path: Path):
    src = tmp_path / "t.c"
    src.write_text("int main(void){return 0;}\n", encoding="utf-8")

    out_t = tmp_path / "only.tokens"
    out = tmp_path / "a.out"

    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            str(src),
            "--dump-tokens-only-to",
            str(out_t),
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out_t.exists()
    assert "int" in out_t.read_text(encoding="utf-8")
    assert not out.exists()
