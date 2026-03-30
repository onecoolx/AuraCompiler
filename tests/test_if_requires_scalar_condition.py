from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_if_requires_scalar_condition(tmp_path):
    # C89: controlling expression of if must have scalar type.
    code = r'''
struct S { int x; };

int main(void) {
  struct S s;
  if (s) {
    return 1;
  }
  return 0;
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("scalar" in e.lower() or "condition" in e.lower() for e in res.errors)
