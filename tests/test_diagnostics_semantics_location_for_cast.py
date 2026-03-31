from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    return Compiler(optimize=False).compile_file(str(c_path), str(out_path))


def test_semantics_diagnostic_has_location_for_invalid_cast(tmp_path):
    code = r"""
struct S { int x; };

int main(void) {
  struct S s;
  return (int)s;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
    assert any(e.startswith("error: semantics:") for e in res.errors)
    assert any("(at " in e and ":?:?:?)" not in e for e in res.errors)
