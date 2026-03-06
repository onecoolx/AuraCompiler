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


def test_ternary_mixed_signed_unsigned_result_type(tmp_path):
    # The conditional operator applies UAC to second/third operands.
    code = textwrap.dedent(
        r"""
        int main(void) {
                unsigned int u = 1u;
                int s = -2;
                /* Ensure the chosen arm is the signed value, so we validate that
                    it gets converted to unsigned (UINT_MAX-1) by ?: UAC. */
                unsigned int r = 0 ? u : s;
            return (r > 10u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_ternary_zero_condition_selects_other_branch(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 123u;
            int s = -1;
            unsigned int r = 0 ? u : s; /* chosen -1 converted to unsigned */
            return (r > 1000u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0
