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


def test_goto_forward_label(tmp_path):
    code = """
int main(){
  goto L;
  return 0;
L:
  return 42;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 42


def test_goto_jump_over_statement(tmp_path):
    code = """
int main(){
  int x = 0;
  goto done;
  x = 1;
 done:
  return x;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_goto_undefined_label_is_error(tmp_path):
    # semantic error
    code = """
int main(){
  goto missing;
  return 0;
}
""".lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
    assert any("Undefined label" in e for e in res.errors)
