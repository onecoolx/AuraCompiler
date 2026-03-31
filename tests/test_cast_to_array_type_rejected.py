from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_cast_to_array_type_rejected(tmp_path):
    # C89: casts require scalar type names; array types are not scalar.
    code = r"""
int main(void) {
  int x = 1;
  (void)(int[])x;
  return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
    assert any("cast" in e.lower() for e in res.errors)
