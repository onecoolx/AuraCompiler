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
    code = r"""
int inc(int x){ return x + 1; }
int dec(int x){ return x - 1; }
int main(){
  int (*a[2])(int);
  a[0] = inc;
  a[1] = dec;
  return a[0](10) == 11 && a[1](10) == 9 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_function_pointer_parameter_and_call(tmp_path):
        code = r"""
int inc(int x){ return x + 1; }
int apply(int (*fp)(int), int x){
    return fp(x);
}
int main(){
    return apply(inc, 3) == 4 ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_function_returning_function_pointer(tmp_path):
        code = r"""
int inc(int x){ return x + 1; }
int (*get(void))(int x){
    return inc;
}
int main(){
    return get()(3) == 4 ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0
