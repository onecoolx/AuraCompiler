"""Tests for multi-declarator statements."""
import subprocess, os, pytest
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, f"Compilation failed: {res.errors}"
    assert os.path.isfile(str(out_path)), "No executable"
    r = subprocess.run([str(out_path)], capture_output=True, timeout=5)
    return r.returncode


def test_int_a_b(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int a,b;a=1;b=2;return a+b;}") == 3


def test_int_a_init_b_init(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int a=1,b=2;return a+b;}") == 3


def test_ptr_and_int(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int x;int *p,y;x=10;p=&x;y=20;return *p+y;}") == 30


def test_global_multi_decl(tmp_path):
    assert _compile_and_run(tmp_path, "int a,b;int main(void){a=1;b=2;return a+b;}") == 3
