from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_incomplete_struct_sizeof_rejected(tmp_path):
    # C89: sizeof on an incomplete type is a constraint violation.
    code = r'''
struct S;

int main(void) {
  return (int)sizeof(struct S);
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("incomplete" in e.lower() or "sizeof" in e.lower() for e in res.errors)
