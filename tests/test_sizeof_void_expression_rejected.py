from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_sizeof_void_expression_is_rejected(tmp_path):
    # Constraint: sizeof operand must not have void type.
    code = r'''
void f(void) {}

int main(void) {
  return (int)sizeof(f());
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("sizeof" in e.lower() and "void" in e.lower() for e in res.errors)
