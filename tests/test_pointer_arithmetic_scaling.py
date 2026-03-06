import subprocess
import sys
from pathlib import Path


def _compile_and_run(tmp_path: Path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    res = subprocess.run(
        [sys.executable, "pycc.py", str(c_path), "-o", str(out_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    run = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return run.returncode


def test_ptr_add_scales_by_sizeof(tmp_path: Path):
    code = r"""
int main(void) {
  char c[4];
  int i[4];
  char *pc = c;
  int *pi = i;

  pc[1] = 11;
  pi[1] = 22;

  if (*((char*)(pc + 1)) != 11) return 1;
  if (*((int*)(pi + 1)) != 22) return 2;
  return 0;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_ptr_index_equiv_ptr_add(tmp_path: Path):
    code = r"""
int main(void) {
  int a[3];
  int *p = a;
  p[1] = 7;
  if (*(p + 1) != 7) return 1;
  if (p[1] != *(p + 1)) return 2;
  return 0;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_ptr_add_scales_address_difference(tmp_path: Path):
        # Avoid direct pointer comparisons (not supported by current semantics).
        # Instead compare the *difference* between (p+1) and (char*)p.
        code = r"""
int main(void) {
    int a[4];
    int *p = a;
    long d = (long)((char*)(p + 1) - (char*)p);
    return d == 4 ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0


def test_ptr_sub_scales_address_difference(tmp_path: Path):
        code = r"""
int main(void) {
    int a[4];
    int *p = a + 2;
    long d = (long)((char*)(p - 1) - (char*)p);
    return d == -4 ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0


def test_ptr_ptr_sub_yields_element_count(tmp_path: Path):
        # Minimal subset: pointers within the same array.
        code = r"""
int main(void) {
    int a[4];
    int *p = a + 3;
    int *q = a + 1;
    long d = (long)(p - q);
    return d == 2 ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0
