from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_address_of_non_lvalue_rejected(tmp_path):
    # C89 constraint: unary & requires an lvalue.
    code = r'''
int main(void) {
  int x;
  int *p = &(x + 1);
  return 0;
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("lvalue" in e.lower() or "address" in e.lower() for e in res.errors)
