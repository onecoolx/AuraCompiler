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


def test_unsigned_right_shift_logical(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 0x80000000u;
            unsigned int r = u >> 1;
            /* logical: 0x40000000 */
            return (r == 0x40000000u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_mixed_shift_promotes_to_unsigned(tmp_path):
    code = textwrap.dedent(
        r"""
        int main(void) {
            unsigned int u = 0x80000000u;
            int s = 1;
            /* u >> s should be unsigned logical shift */
            unsigned int r = u >> s;
            return (r == 0x40000000u) ? 0 : 1;
        }
        """
    ).lstrip()
    assert _compile_and_run(tmp_path, code) == 0
