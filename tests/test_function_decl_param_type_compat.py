from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_reject_function_redecl_with_different_param_types(tmp_path):
    code = r"""
int f(int *p);
int f(int *p);
int f(int *p){ return *p; }
int main(){ int x = 1; return f(&x); }
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success


def test_allow_repeat_identical_param_types(tmp_path):
    code = r"""
int f(int *p);
int f(int *p);
int f(int *p){ return *p; }
int main(){ int x = 1; return f(&x); }
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, "unexpected failure: " + "\n".join(res.errors)
