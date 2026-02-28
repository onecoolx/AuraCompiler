from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str):
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    return p.returncode, p.stdout


def test_printf_with_local_extern_variadic_proto(tmp_path):
    # Regression: function prototypes declared inside a function must still be
    # treated as function symbols, and variadic calls must clear %al per SysV ABI.
    code = r'''
int main(void){
  extern int printf(const char*, ...);
  printf("%d\n", 42);
  return 0;
}
'''.lstrip()
    rc, out = _compile_and_run(tmp_path, code)
    assert rc == 0
    assert out == "42\n"
