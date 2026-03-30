from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_sizeof_bitfield_is_rejected(tmp_path):
    # C89/C99 constraint: cannot apply sizeof to a bit-field.
    # If/when bit-fields are modeled, keep this rejection.
    code = r'''
struct S { unsigned int x:3; };

int main(void) {
  struct S s;
  return sizeof(s.x);
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("bit" in e.lower() and "field" in e.lower() for e in res.errors)
