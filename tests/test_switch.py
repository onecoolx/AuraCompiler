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


def test_switch_basic(tmp_path):
    code = """
int main(){
  int x = 2;
  switch(x){
    case 1: return 1;
    case 2: return 42;
    default: return 0;
  }
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 42


def test_switch_fallthrough_and_break(tmp_path):
    # Case 1 falls through into case 2, then breaks.
    code = """
int main(){
  int x = 1;
  int r = 0;
  switch(x){
    case 1: r = 40;
    case 2: r = r + 2; break;
    default: r = 0;
  }
  return r;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 42


def test_switch_default_only(tmp_path):
    code = """
int main(){
  int x = 9;
  switch(x){
    default: return 42;
  }
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 42
