import pytest

from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code, encoding="utf-8")

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def test_2d_array_decays_to_pointer_to_row_and_scales(tmp_path):
    code = r'''
int main(void){
  char a[2][4];
  char (*p)[4] = a;
  return (((char*)(p + 1) - (char*)p) == 4) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0


def test_2d_array_pointer_deref_sizeof_row(tmp_path):
    code = r'''
int main(void){
  char a[2][4];
  char (*p)[4] = a;
  return (sizeof(*p) == 4) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0
