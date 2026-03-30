from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_alignof_is_rejected_in_c89_subset(tmp_path):
    # Policy: _Alignof/alignof are not supported in this C89-focused compiler.
    code = r'''
int main(void) {
  return _Alignof(int);
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("alignof" in e.lower() or "_alignof" in e.lower() for e in res.errors)
