"""Tests for float global variable initialization."""
import subprocess, os, pytest
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, f"Compilation failed: {res.errors}"
    assert os.path.isfile(str(out_path))
    r = subprocess.run([str(out_path)], capture_output=True, timeout=5)
    return r.returncode


def _compile(tmp_path, code):
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(tmp_path / "t.s"))


def test_float_global_compiles(tmp_path):
    res = _compile(tmp_path, "float g = 3.14f;\nint main(void){return 0;}")
    assert res.success


def test_double_global_compiles(tmp_path):
    res = _compile(tmp_path, "double g = 2.718;\nint main(void){return 0;}")
    assert res.success
