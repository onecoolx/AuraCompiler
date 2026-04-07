"""Tests for wide character L'x' and wide string L"str"."""
import pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code):
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(tmp_path / "t.s"))


def test_wide_char_compiles(tmp_path):
    res = _compile(tmp_path, "int main(void){int x;x=L'A';return x;}")
    assert res.success


def test_wide_string_compiles(tmp_path):
    res = _compile(tmp_path, 'int main(void){char*s=L"AB";return 0;}')
    assert res.success
