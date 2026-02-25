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


def test_enum_basic(tmp_path):
    code = """
enum E { A=40, B=2 };
int main(){
  return A + B;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 42


def test_enum_auto_increment(tmp_path):
    code = """
enum { X=40, Y, Z };
int main(){
  return X + Y; /* 40 + 41 */
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 81
