from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code, encoding="utf-8")

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def test_ternary_unsigned_int_vs_int_result_is_unsigned(tmp_path):
    # If one operand is unsigned int, the result should be unsigned int.
    # 0 ? (unsigned)-1 : 1  == 1
    # 1 ? (unsigned)-1 : 1  == UINT_MAX
    code = r"""
int main(){
    unsigned int a = 0 ? (unsigned int)-1 : 1;
    unsigned int b = 1 ? (unsigned int)-1 : 1;
    if (a != 1U) return 1;
    if (b != (unsigned int)-1) return 2;
    return 0;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_ternary_short_vs_int_promotes_to_int(tmp_path):
    # short and int -> common type should be int, and short arm should be promoted.
    code = r"""
int main(){
    short s = (short)0xFFFF; /* -1 */
    int r = 1 ? s : 0;
    return (r == -1) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_ternary_pointer_and_null(tmp_path):
    # Pointer + null constant: result should be pointer, and null should convert.
    code = r"""
int main(){
    int x = 1;
    int* p = &x;
    int* q = 0 ? p : 0;
    return (q == 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
