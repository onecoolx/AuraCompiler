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


def test_unsigned_division_wrap32(tmp_path):
        # unsigned division differs from signed when top bit set.
        # 0x80000000u / 2u == 0x40000000u
        code = r"""
int main(){
    unsigned int a = (unsigned int)0x80000000U;
    unsigned int c = a / 2U;
    return (c == (unsigned int)0x40000000U) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_division_requires_udiv(tmp_path):
        # This distinguishes signed idiv from unsigned div.
        # 0xFFFFFFFFu / 2u == 2147483647 (0x7FFFFFFF)
        code = r"""
int main(){
    unsigned int a = (unsigned int)0xFFFFFFFFU;
    unsigned int c = a / 2U;
    return (c == (unsigned int)0x7FFFFFFFU) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_division_idiv_bug(tmp_path):
        # With signed division, -1/2 == 0. With unsigned, 0xFFFFFFFF/2 == 0x7FFFFFFF.
        # If the backend accidentally uses signed idiv on a sign-extended value, it will return 0.
        code = r"""
int main(){
    unsigned int a = (unsigned int)-1;
    unsigned int c = a / 2U;
    return (c == (unsigned int)0x7FFFFFFFU) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_division_highbit_value(tmp_path):
        # Force a value with high bit set without relying on large literals.
        # a = 0x80000000u. Unsigned division by 2 gives 0x40000000.
        # Signed idiv on a sign-extended value would yield -1073741824.
        code = r"""
int main(){
    unsigned int a = (unsigned int)-2147483648;
    unsigned int c = a / 2U;
    return (c == (unsigned int)0x40000000U) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_division_needs_zero_extend(tmp_path):
        # Construct a runtime value with high bit set in 32-bit, stored in unsigned int.
        # If the backend loads it with sign-extension and uses signed division, result will be wrong.
        code = r"""
int main(){
    unsigned int a;
    a = 0U;
    a = a - 1U;     /* 0xFFFFFFFF */
    a = a - 2147483647U; /* 0x80000000 */
    a = a - 1U;     /* still 0x7FFFFFFF? (force high-bit path) */
    /* Now create a known high-bit value without literals: 0x80000000 */
    a = 2147483647U + 1U;
    a = a / 2U;
    return (a == 1073741824U) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_modulo(tmp_path):
        # 5u % 2u == 1u
        code = r"""
int main(){
    unsigned int c = 5U % 2U;
    return (c == 1U) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_right_shift_is_logical(tmp_path):
                # Unsigned right shift should be logical (zero-fill).
                code = r"""
int main(){
        unsigned int a = (unsigned int)-1; /* 0xFFFFFFFF */
        unsigned int b = a >> 1;
        return (b == (unsigned int)0x7FFFFFFFU) ? 0 : 1;
}
""".lstrip()
                assert _compile_and_run(tmp_path, code) == 0


def test_signed_right_shift_is_arithmetic(tmp_path):
                # On typical targets (x86-64), signed right shift is arithmetic.
                code = r"""
int main(){
        int a = -1;
        int b = a >> 1;
        return (b == -1) ? 0 : 1;
}
""".lstrip()
                assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_right_shift_of_int_variable(tmp_path):
                # Ensure unsignedness is preserved through variables (loads) during shifts.
                code = r"""
int main(){
        unsigned int a;
        a = (unsigned int)-1;
        a = a >> 1;
        return (a == (unsigned int)0x7FFFFFFFU) ? 0 : 1;
}
""".lstrip()
                assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_compound_add_assign_wrap32(tmp_path):
                # a += b should follow unsigned int arithmetic (wrap modulo 2^32)
                code = r"""
int main(){
        unsigned int a = (unsigned int)-1;
        a += 2U;
        return (a == 1U) ? 0 : 1;
}
""".lstrip()
                assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_compound_div_assign(tmp_path):
                # a /= 2U should use unsigned division
                code = r"""
int main(){
        unsigned int a = (unsigned int)-1;
        a /= 2U;
        return (a == (unsigned int)0x7FFFFFFFU) ? 0 : 1;
}
""".lstrip()
                assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_compound_mod_assign(tmp_path):
                code = r"""
int main(){
        unsigned int a = 5U;
        a %= 2U;
        return (a == 1U) ? 0 : 1;
}
""".lstrip()
                assert _compile_and_run(tmp_path, code) == 0
