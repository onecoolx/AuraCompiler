from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_continue_outside_loop_is_rejected(tmp_path):
    code = r'''
int main(void) {
  continue;
  return 0;
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("continue" in e.lower() for e in res.errors)
