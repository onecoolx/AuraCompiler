import subprocess

from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_signed_char_promotion_then_mul(tmp_path):
    # signed char promotes to int before arithmetic.
    # a = (signed char)0xFF == -1; (-1) * 2 == -2; returned mod 256 -> 254
    code = r'''
int main(){
    signed char a = (signed char)255;
    int b = a * 2;
    return b;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 254
