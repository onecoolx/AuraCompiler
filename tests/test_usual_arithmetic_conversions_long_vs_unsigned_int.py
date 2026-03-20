from __future__ import annotations


import subprocess


from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_file = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_file.write_text(code)

    compiler = Compiler(optimize=False)
    res = compiler.compile_file(str(c_file), str(out_path))
    assert res.success, f"compile failed: {res.errors}\nASM:\n{res.assembly}"

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_uac_long_vs_unsigned_int_prefers_long_on_lp64(tmp_path):
    # C89 usual arithmetic conversions: long (signed) vs unsigned int.
    # On LP64, long can represent all values of unsigned int, so the common
    # type is long (signed). Thus (long)-1 < 1U is true.
    code = r"""
int main(void){
    long s = -1L;
    unsigned int u = 1U;
    return (s < u) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_unsigned_int_vs_long_prefers_long_on_lp64(tmp_path):
    # Same as above but reversed operands.
    code = r"""
int main(void){
    unsigned int u = 1U;
    long s = -1L;
    return (u > s) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_long_vs_unsigned_int_arithmetic_in_long(tmp_path):
    # If common type is long, then 0xFFFFFFFFU + (long)-1 == 0xFFFFFFFE (in long)
    # and is > 0.
    code = r"""
int main(void){
    unsigned int u = 0xFFFFFFFFU;
    long s = -1L;
    long x = u + s;
    return (x == 0xFFFFFFFEL && x > 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
