from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_function_void_param_means_zero_params(tmp_path):
    code = r'''
int f(void) { return 0; }
int main(void) { return f(); }
'''.lstrip()

    res = _compile(tmp_path, code)
    assert res.success, "compile failed: " + "\n".join(res.errors)
