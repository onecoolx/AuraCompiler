from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_char_array_too_small_for_string_literal_is_error(tmp_path: Path) -> None:
    # "abc" requires 4 bytes including the terminating NUL.
    code = r"""
int main(void){
  char s[3] = "abc";
  return s[0];
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_char_array_exact_fit_for_string_literal_is_ok(tmp_path: Path) -> None:
    code = r"""
int main(void){
  char s[4] = "abc";
  return (s[0]=='a' && s[1]=='b' && s[2]=='c' && s[3]==0) ? 0 : 1;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, res.errors
