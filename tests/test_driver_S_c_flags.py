from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_S_flag_emits_s(tmp_path):
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void) { return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    out_s = tmp_path / "out.s"
    r = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), str(c_path), "-S", "-o", str(out_s)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out_s.exists()
    assert out_s.read_text(encoding="utf-8").startswith(".text")


def test_driver_c_flag_emits_o(tmp_path):
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void) { return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    out_o = tmp_path / "out.o"
    r = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), str(c_path), "-c", "-o", str(out_o)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out_o.exists()

    # Sanity: system `file` should recognize ELF relocatable on Linux.
    fr = subprocess.run(
        ["file", str(out_o)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert fr.returncode == 0, fr.stderr
    assert "relocatable" in fr.stdout.lower()


def test_driver_default_output_names_without_o(tmp_path):
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void) { return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    # -S without -o -> t.s (in current working directory)
    r1 = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), str(c_path), "-S"],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r1.returncode == 0, (r1.stdout, r1.stderr)
    assert (tmp_path / "t.s").exists()

    # -c without -o -> t.o (in current working directory)
    r2 = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), str(c_path), "-c"],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r2.returncode == 0, (r2.stdout, r2.stderr)
    assert (tmp_path / "t.o").exists()
