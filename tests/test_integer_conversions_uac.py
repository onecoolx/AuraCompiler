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


def test_uac_mixed_signed_unsigned_add(tmp_path):
    # In C89, usual arithmetic conversions convert to unsigned if ranks equal and one is unsigned.
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 1u;
            int s = -2;
            /* u + s => unsigned, result is 0xFFFFFFFF (wrap), which is > 10u */
            unsigned int r = u + s;
            return (r > 10u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_mixed_signed_unsigned_sub(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 0u;
            int s = 1;
            unsigned int r = u - s; /* wrap to UINT_MAX */
            return (r > 100u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_mixed_signed_unsigned_mul(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 4000000000u;
            int s = 2;
            unsigned int r = u * s;
            /* Just validate we didn't treat this as signed overflow behavior. */
            return (r == 3705032704u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_shift_right_unsigned_is_logical(tmp_path):
    # Unsigned right shift should be logical.
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 0x80000000u;
            unsigned int r = u >> 31;
            return (r == 1u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0
