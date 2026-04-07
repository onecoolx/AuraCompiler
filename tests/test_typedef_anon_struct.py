"""Tests for typedef anonymous struct/union."""
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


def test_typedef_anon_struct(tmp_path):
    code = "typedef struct{int x;int y;}Point;int main(void){Point p;p.x=1;p.y=2;return p.x+p.y;}"
    assert _compile_and_run(tmp_path, code) == 3


def test_typedef_named_struct(tmp_path):
    code = "typedef struct S{int x;}T;int main(void){T t;t.x=42;return t.x;}"
    assert _compile_and_run(tmp_path, code) == 42
