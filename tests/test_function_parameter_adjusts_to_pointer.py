from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    return __import__("subprocess").run([str(out_path)], check=False).returncode


def test_function_parameter_adjusts_to_pointer(tmp_path):
    # C89: parameter declarator "int f()" adjusts to "int (*f)()".
    code = r'''
int callee(void) { return 42; }

int apply(int f()) {
  return f();
}

int main(void) {
  return apply(callee) == 42 ? 0 : 1;
}
'''.lstrip()

    assert _compile_and_run(tmp_path, code) == 0
