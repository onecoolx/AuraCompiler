"""Tests for adjacent string literal concatenation."""
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


def test_two_strings(tmp_path):
    assert _compile_and_run(tmp_path, 'int main(void){char*s="hel" "lo";return s[0]==104?0:1;}') == 0


def test_three_strings(tmp_path):
    assert _compile_and_run(tmp_path, 'int main(void){char*s="a" "b" "c";return s[2]==99?0:1;}') == 0


def test_string_with_escape(tmp_path):
    code = r'int main(void){char*s="ab\n" "cd";return s[2]==10?0:1;}'
    assert _compile_and_run(tmp_path, code) == 0
