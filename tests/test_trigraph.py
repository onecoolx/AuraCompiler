"""Tests for trigraph replacement."""
import pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code):
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(tmp_path / "t.s"))


def test_trigraph_define(tmp_path):
    # ??= -> #
    res = _compile(tmp_path, "??=define X 42\nint main(void){return X;}")
    assert res.success


def test_trigraph_braces(tmp_path):
    # ??< -> {  ??> -> }
    res = _compile(tmp_path, "int main(void)??<return 0;??>")
    assert res.success


def test_non_trigraph_unaffected(tmp_path):
    # ?? followed by non-trigraph char should not be replaced
    res = _compile(tmp_path, 'int main(void){char*s="??x";return 0;}')
    assert res.success
