from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_int_pointer_add_scaling(tmp_path):
    # Verify that p+1 advances by sizeof(int) bytes.
    code = r'''
int main(){
  int a[3];
  int *p;
  a[0] = 7;
  a[1] = 42;
  a[2] = 9;
  p = a;
    return p[1];
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 42
