import textwrap

from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], capture_output=True)
    return p.returncode


def test_unsigned_int_compare_uses_32bit_semantics(tmp_path):
    # Regression guard: if we accidentally compare zero-extended UINT32 values
    # as signed 64-bit, the high bit can flip the sign and break `>`.
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int x = 0xffffffffu;
            unsigned int y = 10u;
            return (x > y) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_int_compare_lt(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int x = 0x80000000u;
            unsigned int y = 0xffffffffu;
            return (x < y) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0
