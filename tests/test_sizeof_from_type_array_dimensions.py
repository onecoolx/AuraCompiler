"""Tests for sizeof computation using Type.array_dimensions (task 6.2).

Validates that sizeof(array_variable) computes the total byte size from
Type.is_array / array_dimensions / array_element_type rather than relying
solely on _local_array_dims or _var_types string parsing.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pycc.compiler import Compiler


def _compile_and_run(tmp_path: Path, c_src: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_sizeof_1d_int_array(tmp_path: Path) -> None:
    """sizeof(int arr[10]) == 40."""
    code = "int main(void){ int arr[10]; return sizeof(arr) == 40 ? 0 : 1; }"
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_1d_char_array(tmp_path: Path) -> None:
    """sizeof(char buf[64]) == 64."""
    code = "int main(void){ char buf[64]; return sizeof(buf) == 64 ? 0 : 1; }"
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_1d_pointer_array(tmp_path: Path) -> None:
    """sizeof(int *ptrs[5]) == 40 on x86-64."""
    code = "int main(void){ int *ptrs[5]; return sizeof(ptrs) == 40 ? 0 : 1; }"
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_2d_array(tmp_path: Path) -> None:
    """sizeof(int m[3][4]) == 48."""
    code = "int main(void){ int m[3][4]; return sizeof(m) == 48 ? 0 : 1; }"
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_array_of_long(tmp_path: Path) -> None:
    """sizeof(long arr[3]) == 24 on x86-64."""
    code = "int main(void){ long arr[3]; return sizeof(arr) == 24 ? 0 : 1; }"
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_array_of_short(tmp_path: Path) -> None:
    """sizeof(short arr[8]) == 16."""
    code = "int main(void){ short arr[8]; return sizeof(arr) == 16 ? 0 : 1; }"
    assert _compile_and_run(tmp_path, code) == 0
