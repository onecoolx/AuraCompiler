"""Property tests: hide-set macro expansion termination and correctness (Property 13)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_self_referencing_object_macro_terminates(tmp_path):
    code = "#define A A\nA\n"
    out = _preprocess(tmp_path, code)
    assert "A" in out  # A should remain unexpanded


def test_mutual_recursion_terminates(tmp_path):
    code = "#define A B\n#define B A\nA\n"
    out = _preprocess(tmp_path, code)
    # Should terminate; result is either A or B (not infinite)
    assert len(out) < 1000


def test_function_macro_self_reference_terminates(tmp_path):
    code = "#define F(x) F(x)\nF(1)\n"
    out = _preprocess(tmp_path, code)
    assert "F" in out  # F should remain after one expansion
