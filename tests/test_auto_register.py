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


def test_auto_storage_class_local(tmp_path):
    code = r'''
int main(){
  auto int x;
  x = 41;
  return x + 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 42


def test_register_storage_class_local(tmp_path):
    code = r'''
int main(){
  register int x;
  x = 6;
  return x * 7;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 42
