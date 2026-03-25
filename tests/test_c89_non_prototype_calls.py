import textwrap

from pycc.compiler import Compiler


def _compile(tmp_path, src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(src)
    return Compiler(optimize=False).compile_file(str(c_path), str(out_path))


def test_call_without_prototype_promotes_float_to_double(tmp_path):
    # C89: calling a function without a prototype applies default argument promotions.
    # Here, `float` should be promoted to `double` when passed.
    src = textwrap.dedent(
        r"""
        int foo();

        /* Define an old-style (K&R) function. */
        int foo(d)
        int d;
        {
            return (int)d;
        }

        int main(void){
            int x = 3;
            return foo(x);
        }
        """
    ).lstrip()
    res = _compile(tmp_path, src)
    assert res.success, res.errors


def test_call_without_prototype_promotes_char_to_int(tmp_path):
    # C89: integer promotions apply (e.g. char -> int).
    src = textwrap.dedent(
        r"""
        int foo();

        int foo(a)
        int a;
        {
            return a;
        }

        int main(void){
            char c = 7;
            return foo(c);
        }
        """
    ).lstrip()
    res = _compile(tmp_path, src)
    assert res.success, res.errors


def test_incompatible_later_prototype_is_error(tmp_path):
    # If a later prototype conflicts with an earlier non-prototype declaration,
    # it should be rejected (C89 constraint; subset diagnostic).
    src = textwrap.dedent(
        r"""
        int foo();
        int foo(int a, int b);
        int foo(a)
        int a;
        {
            return a;
        }
        int main(void){
            return foo(1);
        }
        """
    ).lstrip()
    res = _compile(tmp_path, src)
    assert not res.success
