import subprocess

from pathlib import Path


def test_driver_multiple_inputs_single_output(tmp_path):
    # Verify the CLI driver can take multiple .c inputs and produce a single executable.
    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    out = tmp_path / "a.out"

    a.write_text(
        r"""
extern int get(void);
int main(){
  return get() == 42 ? 0 : 1;
}
""".lstrip()
    )

    b.write_text(
        r"""
int get(void){
  return 42;
}
""".lstrip()
    )

    repo_root = Path(__file__).resolve().parents[1]

    # Run from repo root so relative 'pycc.py' resolves.
    p = subprocess.run(
      ["python", "pycc.py", str(a), str(b), "-o", str(out)],
      cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr

    r = subprocess.run([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0
