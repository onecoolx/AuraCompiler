from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_switch_requires_integer_controlling_expression(tmp_path):
    # C89: controlling expression of switch must have integer type.
    code = r'''
int main(void) {
  double d = 1.0;
  switch (d) {
    case 1: return 0;
    default: return 1;
  }
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("switch" in e.lower() and ("integer" in e.lower() or "int" in e.lower()) for e in res.errors)
