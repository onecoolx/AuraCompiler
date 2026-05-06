from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    return Compiler(optimize=False).compile_file(str(c_path), str(out_path))


def test_semantics_diagnostic_has_location_for_invalid_sizeof(tmp_path):
    code = r"""
int main(void) {
  return (int)sizeof((void)0);
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
    # GCC-compatible format: <file>:<line>:<col>: error: semantics: <message>
    assert any("error: semantics:" in e for e in res.errors)
    assert any("t.c:" in e for e in res.errors)
