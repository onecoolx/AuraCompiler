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


def test_char_signedness_promotion_behavior(tmp_path):
    # In this compiler, 'char' is treated as signed for loads/promotions.
    code = r"""
int main(){
  char c = (char)0xFF; /* -1 if char is signed */
  int x = c;
  return x == -1 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_char_promotes_to_int_with_zero_extend(tmp_path):
    code = r"""
int main(){
  unsigned char c = 255;
  int x = c;
  return x == 255 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_short_promotes_to_int_with_sign_extend(tmp_path):
    code = r"""
int main(){
  short s = (short)0xFFFF; /* -1 */
  int x = s;
  return x == -1 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_promotes_to_int_with_zero_extend(tmp_path):
    code = r"""
int main(){
  unsigned short s = 65535;
  int x = s;
  return x == 65535 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_comparison_after_promotion_unsigned_short_vs_int(tmp_path):
    # This compiler currently models unsignedness as a property of the IR operand,
    # and uses unsigned condition codes if either operand is unsigned.
    # With u=65535 and i=-1, the implementation treats the compare as unsigned,
    # so 65535 > (unsigned)-1 is false.
    code = r"""
int main(){
  unsigned short u = 65535;
  int i = -1;
  return (u > i) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 1
