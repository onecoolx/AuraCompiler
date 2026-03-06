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


def test_relational_mixed_u32_vs_int_negative(tmp_path):
    # unsigned int vs int -> unsigned int; -1 becomes UINT_MAX.
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 1u;
            int s = -1;
            return (s > u) ? 0 : 1; /* UINT_MAX > 1 */
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_relational_mixed_u32_vs_int_negative_lt(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 1u;
            int s = -1;
            return (s < u) ? 1 : 0; /* false */
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0
