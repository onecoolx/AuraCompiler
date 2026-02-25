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


def test_logical_and_short_circuit_skips_rhs(tmp_path):
    code = """
int g;
int side(){ g = g + 1; return 1; }
int main(){
  g = 0;
  if (0 && side()) { }
  return g;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_logical_or_short_circuit_skips_rhs(tmp_path):
    code = """
int g;
int side(){ g = g + 1; return 0; }
int main(){
  g = 0;
  if (1 || side()) { }
  return g;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_logical_and_evaluates_rhs_when_needed(tmp_path):
    code = """
int g;
int side(){ g = g + 1; return 1; }
int main(){
  g = 0;
  if (1 && side()) { }
  return g;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 1


def test_logical_or_evaluates_rhs_when_needed(tmp_path):
    code = """
int g;
int side(){ g = g + 1; return 1; }
int main(){
  g = 0;
  if (0 || side()) { }
  return g;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 1
