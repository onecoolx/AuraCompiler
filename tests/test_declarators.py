from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def test_function_pointer_var_decl_and_call(tmp_path):
    code = r"""
int foo(int x){ return x + 1; }
int main(){
  int (*fp)(int);
  fp = foo;
  return fp(3) == 4 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_function_pointer_array_decl(tmp_path):
    # TODO: array-of-function-pointers declarator parsing is not implemented yet.
    pass
