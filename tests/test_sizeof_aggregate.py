"""Tests for sizeof(struct/union)."""
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


def test_sizeof_struct(tmp_path):
    # struct with two ints = 8 bytes on x86-64
    assert _compile_and_run(tmp_path, "struct S{int x;int y;};int main(void){return sizeof(struct S);}") == 8


def test_sizeof_union(tmp_path):
    # union size = max member = int = 4 bytes (aligned to 4)
    code = "union U{int i;char c;};int main(void){return sizeof(union U);}"
    assert _compile_and_run(tmp_path, code) == 4


def test_sizeof_struct_with_padding(tmp_path):
    # struct { char c; int i; } = 8 bytes (1 + 3 padding + 4)
    code = "struct S{char c;int i;};int main(void){return sizeof(struct S);}"
    assert _compile_and_run(tmp_path, code) == 8
