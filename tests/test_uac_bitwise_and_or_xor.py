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


def test_uac_bitwise_and_mixed_signed_unsigned(tmp_path):
    # Ensure mixed signed/unsigned operands yield unsigned behavior.
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 0x80000000u;
            int s = -1;
            unsigned int r = u & s;
            return (r == 0x80000000u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_bitwise_or_mixed_signed_unsigned(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 0x80000000u;
            int s = 1;
            unsigned int r = u | s;
            return (r == 0x80000001u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_bitwise_xor_mixed_signed_unsigned(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 0xffffffffu;
            int s = -1;
            unsigned int r = u ^ s;
            return (r == 0u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0
