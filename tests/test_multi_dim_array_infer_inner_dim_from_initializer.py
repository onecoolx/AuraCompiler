from __future__ import annotations


import subprocess


from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code, encoding="utf-8")

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def test_local_2d_array_infer_inner_dim_from_brace_initializer(tmp_path):
    # C89: in `T a[][N] = {...}`, the first dimension may be omitted and is
    # inferred from the initializer. The inner dimension must be known.
    # Here we omit the first dimension and expect it to become 2.
    code = r"""
int main(void){
  char a[][4] = { {1,2,3,4}, {5,6,7,8} };
  return (sizeof(a) == 8 && a[1][2] == 7) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
