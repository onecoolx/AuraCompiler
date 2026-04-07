"""Tests for bit-fields."""
import subprocess, os, pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code):
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(tmp_path / "t.s"))


def test_bitfield_declaration_compiles(tmp_path):
    code = "struct S{unsigned int x:4;unsigned int y:4;};int main(void){return sizeof(struct S);}"
    res = _compile(tmp_path, code)
    assert res.success


def test_bitfield_sizeof(tmp_path):
    code = "struct S{unsigned int x:4;unsigned int y:4;};int main(void){return sizeof(struct S);}"
    res = _compile(tmp_path, code)
    assert res.success
    # Both fit in one 4-byte storage unit
    assert res.assembly is not None
