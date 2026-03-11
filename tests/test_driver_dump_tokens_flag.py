from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_dump_tokens_writes_file(tmp_path):
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void){ return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    out = tmp_path / "a.out"
    r = subprocess.run(
        [
            "python",
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "--dump-tokens",
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    tok_path = tmp_path / "pycc-tmp.tokens"
    assert tok_path.exists()
    txt = tok_path.read_text(encoding="utf-8")
    # Should contain at least the 'int' keyword token.
    assert "int" in txt
    assert out.exists()
