"""Tests for ++/-- operators (pre/post increment/decrement)."""
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


def _compile(tmp_path, code):
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(tmp_path / "t"))


def test_pre_increment(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int x;x=5;++x;return x;}") == 6


def test_pre_increment_value(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int x;x=5;return ++x;}") == 6


def test_post_increment(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int x;x=5;x++;return x;}") == 6


def test_post_increment_value(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int x;x=5;return x++;}") == 5


def test_pre_decrement(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int x;x=5;return --x;}") == 4


def test_post_decrement_value(tmp_path):
    assert _compile_and_run(tmp_path, "int main(void){int x;x=5;return x--;}") == 5


def test_for_loop_with_increment(tmp_path):
    code = "int main(void){int i;int s;s=0;for(i=0;i<5;i++)s=s+i;return s;}"
    assert _compile_and_run(tmp_path, code) == 10


def test_for_loop_with_decrement(tmp_path):
    code = "int main(void){int i;int s;s=0;for(i=4;i>=0;i--)s=s+i;return s;}"
    assert _compile_and_run(tmp_path, code) == 10


def test_while_with_increment(tmp_path):
    code = "int main(void){int i;i=0;while(i<5)i++;return i;}"
    assert _compile_and_run(tmp_path, code) == 5


def test_const_increment_rejected(tmp_path):
    res = _compile(tmp_path, "int main(void){const int x=5;++x;return x;}")
    assert not res.success
