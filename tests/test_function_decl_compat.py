from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_reject_function_redecl_with_different_param_count(tmp_path):
    code = r"""
int f(int a);
int f(int a, int b);
int f(int a){ return a; }
int main(){ return f(1); }
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_reject_function_redecl_with_different_return_type(tmp_path):
    code = r"""
int f(int a);
char f(int a);
int f(int a){ return a; }
int main(){ return f(1); }
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_allow_repeat_identical_prototypes(tmp_path):
    code = r"""
int f(int a);
int f(int a);
int f(int a){ return a + 1; }
int main(){ return f(41); }
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success


def test_allow_prototype_then_definition(tmp_path):
    code = r"""
int add(int a, int b);
int add(int a, int b){ return a + b; }
int main(){ return add(40, 2); }
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success
