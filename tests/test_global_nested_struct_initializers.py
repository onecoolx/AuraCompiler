import subprocess
import textwrap


def _compile_and_run(code: str) -> subprocess.CompletedProcess:
    p = subprocess.run(
        ["python", "pycc.py", "-", "-o", "a.out"],
        input=code.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", errors="replace")

    r = subprocess.run(["./a.out"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r


def test_global_nested_struct_zero_fill() -> None:
    # NOTE: currently fails because global const-initializer blob packing does
    # not yet place nested aggregate fields at the correct offsets.
    # Kept as an xfail to drive the next milestone.
    code = textwrap.dedent(
        r"""
        struct B { int x; int y; };
        struct A { int a; struct B b; int c; };

        struct A g = { 1, { 2 } };

        int main(void) {
            if (g.a != 1) return 1;
            if (g.b.x != 2) return 2;
            if (g.b.y != 0) return 3;
            if (g.c != 0) return 4;
            return 0;
        }
        """
    )

    r = _compile_and_run(code)
    assert r.returncode == 0, (r.stdout.decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace"))


def test_global_nested_struct_brace_elision() -> None:
    # C89 brace elision: scalar initializer for nested aggregate initializes its first member.
    code = textwrap.dedent(
        r"""
        struct B { int x; int y; };
        struct A { int a; struct B b; int c; };

        struct A g = { 1, 2, 3 };

        int main(void) {
            if (g.a != 1) return 1;
            if (g.b.x != 2) return 2;
            if (g.b.y != 3) return 3;
            if (g.c != 0) return 4;
            return 0;
        }
        """
    )

    r = _compile_and_run(code)
    assert r.returncode == 0
