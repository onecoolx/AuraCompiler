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


def test_uac_unsigned_int_plus_signed_int_promotes_to_unsigned(tmp_path):
    # Usual arithmetic conversions: if either operand is unsigned int,
    # the other is converted to unsigned int.
    # (unsigned)-1 + 2u == 1u
    code = r"""
int main(){
    unsigned int u = (unsigned int)-1;
    int s = 2;
    unsigned int r = u + s;
    return (r == 1U) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_unsigned_short_plus_int_yields_int(tmp_path):
    # Integer promotions: unsigned short -> int (on 32-bit int targets).
    # Then UAC: int + int -> int.
    # 65535 + 1 == 65536
    code = r"""
int main(){
    unsigned short u = 65535;
    int s = 1;
    int r = u + s;
    return (r == 65536) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
