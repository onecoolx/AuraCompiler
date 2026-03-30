from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_prototype_call_wrong_arity_rejected(tmp_path):
    code = r'''
int f(int a, int b) { return a + b; }

int main(void) {
  return f(1);
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("argument" in e.lower() or "arity" in e.lower() or "parameter" in e.lower() for e in res.errors)
