from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_unsigned_char_promotion_add(tmp_path):
    # (unsigned char)250 + 10 => 260, returned mod 256 => 4
    code = r"""
int main(){
  unsigned char a = 250;
  int b = 10;
  return a + b;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 4


def test_signed_char_promotion_negative(tmp_path):
    # signed char -1 promotes to int -1; (-1)+2 => 1
    code = r"""
int main(){
  signed char a = (signed char)255;
  return a + 2;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 1


def test_unsigned_int_vs_int_comparison(tmp_path):
    # usual arithmetic conversions: -1 converted to unsigned, so (-1 < 1u) is false
    code = r"""
int main(){
  int a = -1;
  unsigned int b = 1U;
  return (a < b) ? 1 : 0;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_addition_wrap32(tmp_path):
        # unsigned int arithmetic is modulo 2^32: (0xFFFFFFFFu + 2u) == 1u
        code = r"""
int main(){
    unsigned int a = (unsigned int)0xFFFFFFFFU;
    unsigned int b = 2U;
    unsigned int c = a + b;
    return (c == 1U) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_multiplication_wrap32(tmp_path):
        # 0x80000000u * 2u == 0u (wrap)
        code = r"""
int main(){
    unsigned int a = (unsigned int)0x80000000U;
    unsigned int c = a * 2U;
    return (c == 0U) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0
