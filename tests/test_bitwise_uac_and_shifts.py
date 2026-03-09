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


def test_unsigned_short_or_int_promotes_to_int(tmp_path):
    # unsigned short integer-promotes to int on this target.
    # 0x00FF | 0x0100 == 0x01FF
    code = r"""
int main(){
    unsigned short u = 0x00FF;
    int r = u | 0x0100;
    return (r == 0x01FF) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_right_shift_value_promotes_then_shifts(tmp_path):
    # Promotion first: unsigned short 0x8000 -> int 32768, then >> 1 == 16384.
    code = r"""
int main(){
    unsigned short u = 0x8000;
    int r = u >> 1;
    return (r == 16384) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_signed_short_right_shift_arithmetic_after_promotion(tmp_path):
    # signed short -2 promotes to int -2; arithmetic shift keeps sign.
    code = r"""
int main(){
    short s = -2;
    int r = s >> 1;
    return (r == -1) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_compound_shift_assign_on_unsigned_short(tmp_path):
    # Compound assignment must behave as if: u = (unsigned short)( (int)u >> 1 );
    # Here u starts 0x8000 -> promotes to int 32768 -> >>1 = 16384 -> cast back keeps 0x4000.
    code = r"""
int main(){
    unsigned short u = 0x8000;
    u >>= 1;
    return (u == 0x4000) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_compound_shift_assign_on_signed_short(tmp_path):
    # signed short -2 >> 1 == -1, stored back into short should remain -1.
    code = r"""
int main(){
    short s = -2;
    s >>= 1;
    return (s == -1) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
