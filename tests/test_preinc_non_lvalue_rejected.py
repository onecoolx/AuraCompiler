from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_preinc_non_lvalue_rejected(tmp_path):
    # C89 constraint: ++ requires a modifiable lvalue.
    code = r'''
int main(void) {
  int x;
  ++(x + 1);
  return 0;
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("lvalue" in e.lower() or "modifiable" in e.lower() or "++" in e for e in res.errors)
