"""Tests for pycc.toolchain — Toolchain class and helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from pycc.toolchain import Toolchain, _first_existing, _probe_gcc_crt, _probe_gcc_lib_dirs


# ------------------------------------------------------------------
# Unit tests for helper functions
# ------------------------------------------------------------------

def test_first_existing_returns_first_match(tmp_path: Path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    assert _first_existing([str(a), str(b)]) == str(a)


def test_first_existing_skips_missing(tmp_path: Path):
    a = tmp_path / "missing.txt"
    b = tmp_path / "exists.txt"
    b.write_text("b")
    assert _first_existing([str(a), str(b)]) == str(b)


def test_first_existing_returns_none_when_all_missing(tmp_path: Path):
    assert _first_existing([str(tmp_path / "x"), str(tmp_path / "y")]) is None


def test_probe_gcc_crt_returns_tuple():
    cb, ce = _probe_gcc_crt()
    # On a system with gcc installed, both should be strings.
    # On a minimal system, both may be None.
    if cb is not None:
        assert os.path.exists(cb)
        assert ce is not None and os.path.exists(ce)
    else:
        assert ce is None


def test_probe_gcc_lib_dirs_returns_list():
    dirs = _probe_gcc_lib_dirs()
    assert isinstance(dirs, list)
    for d in dirs:
        assert os.path.isdir(d)


# ------------------------------------------------------------------
# Toolchain probing
# ------------------------------------------------------------------

def test_toolchain_probe_dynamic_linker():
    tc = Toolchain()
    dl = tc.probe_dynamic_linker()
    # On a standard Linux system this should be found.
    if dl is not None:
        assert os.path.exists(dl)


def test_toolchain_probe_crt_files():
    tc = Toolchain()
    crt = tc.probe_crt_files()
    assert isinstance(crt, dict)
    valid_keys = {"crt1", "crti", "crtn", "crtbegin", "crtend", "crtbeginS", "crtendS"}
    for key in crt:
        assert key in valid_keys
        assert os.path.exists(crt[key])


def test_toolchain_probe_lib_dirs():
    tc = Toolchain()
    dirs = tc.probe_lib_dirs()
    assert isinstance(dirs, list)
    for d in dirs:
        assert os.path.isdir(d)


# ------------------------------------------------------------------
# Toolchain env override
# ------------------------------------------------------------------

def test_toolchain_respects_env_vars(monkeypatch):
    monkeypatch.setenv("PYCC_AS", "/custom/as")
    monkeypatch.setenv("PYCC_LD", "/custom/ld")
    tc = Toolchain()
    assert tc.assembler == "/custom/as"
    assert tc.linker == "/custom/ld"


def test_toolchain_constructor_overrides_env(monkeypatch):
    monkeypatch.setenv("PYCC_AS", "/env/as")
    tc = Toolchain(assembler="/explicit/as")
    assert tc.assembler == "/explicit/as"


# ------------------------------------------------------------------
# build_link_cmd
# ------------------------------------------------------------------

def test_build_link_cmd_produces_ld_command(tmp_path: Path):
    tc = Toolchain()
    # Skip if no glibc dev on this system.
    crt = tc.probe_crt_files()
    if len(crt) < 5:
        pytest.skip("glibc dev files not found")
    cmd = tc.build_link_cmd(["/tmp/a.o"], str(tmp_path / "a.out"))
    assert cmd[0] == "ld"
    assert "-dynamic-linker" in cmd
    assert "-lc" in cmd
    assert "/tmp/a.o" in cmd


def test_build_link_cmd_extra_libs(tmp_path: Path):
    tc = Toolchain()
    crt = tc.probe_crt_files()
    if len(crt) < 5:
        pytest.skip("glibc dev files not found")
    cmd = tc.build_link_cmd(
        ["/tmp/a.o"], str(tmp_path / "a.out"),
        extra_libs=["m", "pthread"],
    )
    assert "-lm" in cmd
    assert "-lpthread" in cmd


def test_build_link_cmd_shared_flag(tmp_path: Path):
    tc = Toolchain()
    crt = tc.probe_crt_files()
    if len(crt) < 5:
        pytest.skip("glibc dev files not found")
    cmd = tc.build_link_cmd(
        ["/tmp/a.o"], str(tmp_path / "a.out"),
        shared=True,
    )
    assert "-shared" in cmd
    # Shared libraries should NOT have crt1.o or -dynamic-linker.
    assert "-dynamic-linker" not in cmd


def test_build_link_cmd_no_gcc_in_command(tmp_path: Path):
    """The whole point: no gcc dependency in the link command."""
    tc = Toolchain()
    crt = tc.probe_crt_files()
    if len(crt) < 5:
        pytest.skip("glibc dev files not found")
    cmd = tc.build_link_cmd(["/tmp/a.o"], str(tmp_path / "a.out"))
    assert "gcc" not in cmd


# ------------------------------------------------------------------
# End-to-end: assemble + link via Toolchain
# ------------------------------------------------------------------

def test_toolchain_assemble_and_link(tmp_path: Path):
    """Assemble a trivial program and link it using Toolchain only."""
    tc = Toolchain()
    crt = tc.probe_crt_files()
    if len(crt) < 5:
        pytest.skip("glibc dev files not found")

    asm = tmp_path / "test.s"
    asm.write_text(
        ".text\n"
        ".globl main\n"
        "main:\n"
        "  xorl %eax, %eax\n"
        "  ret\n"
    )
    obj = tmp_path / "test.o"
    exe = tmp_path / "test"

    tc.run_assemble(str(asm), str(obj))
    assert obj.exists()

    cmd = tc.build_link_cmd([str(obj)], str(exe))
    tc.run_link(cmd)
    assert exe.exists()

    result = subprocess.run([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0


def test_toolchain_link_with_extra_lib(tmp_path: Path):
    """Link a program that calls sqrt via -lm using Toolchain."""
    tc = Toolchain()
    crt = tc.probe_crt_files()
    if len(crt) < 5:
        pytest.skip("glibc dev files not found")

    # Use the Compiler to produce an object file, then link with Toolchain.
    from pycc.compiler import Compiler
    src = tmp_path / "math_test.c"
    src.write_text(
        '#include <math.h>\n'
        'int main(void) {\n'
        '  double x = sqrt(4.0);\n'
        '  return (int)x == 2 ? 0 : 1;\n'
        '}\n'
    )
    obj = tmp_path / "math_test.o"
    exe = tmp_path / "math_test"

    cc = Compiler(optimize=False, use_system_cpp=True)
    res = cc.compile_file(str(src), str(obj))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    cmd = tc.build_link_cmd([str(obj)], str(exe), extra_libs=["m"])
    tc.run_link(cmd)
    assert exe.exists()

    result = subprocess.run([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0


# ------------------------------------------------------------------
# CLI integration: pycc links .o without gcc
# ------------------------------------------------------------------

def test_pycc_cli_links_object_without_gcc(tmp_path: Path):
    """pycc foo.o -o foo should use ld, not gcc."""
    from pycc.compiler import Compiler

    src = tmp_path / "hello.c"
    src.write_text('int main(void) { return 42; }\n')
    obj = tmp_path / "hello.o"
    exe = tmp_path / "hello"

    cc = Compiler(optimize=False)
    res = cc.compile_file(str(src), str(obj))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    tc = Toolchain()
    crt = tc.probe_crt_files()
    if len(crt) < 5:
        pytest.skip("glibc dev files not found")
    cmd = tc.build_link_cmd([str(obj)], str(exe))
    tc.run_link(cmd)
    assert exe.exists()

    result = subprocess.run([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 42
