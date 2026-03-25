import textwrap

from pycc.compiler import Compiler


def _compile(tmp_path, src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(src)
    return Compiler(optimize=False).compile_file(str(c_path), str(out_path))


def test_knr_function_definition_basic(tmp_path):
    # C89 old-style (K&R) function definition.
    src = textwrap.dedent(
        r"""
        int f(a, b)
        int a;
        char b;
        {
            return a + b;
        }

        int main(void){
            return f(40, 2);
        }
        """
    ).lstrip()
    res = _compile(tmp_path, src)
    assert res.success, res.errors


def test_knr_function_missing_param_decl_defaults_to_int(tmp_path):
    # In C89, an undeclared parameter type defaults to int.
    src = textwrap.dedent(
        r"""
        int f(a, b)
        int a;
        {
            return a + b;
        }

        int main(void){
            return f(40, 2);
        }
        """
    ).lstrip()
    res = _compile(tmp_path, src)
    assert res.success, res.errors


def test_knr_function_extra_param_decl_is_error(tmp_path):
    src = textwrap.dedent(
        r"""
        int f(a)
        int a;
        int b;
        {
            return a;
        }
        """
    ).lstrip()
    res = _compile(tmp_path, src)
    assert not res.success


def test_knr_function_duplicate_param_decl_is_error(tmp_path):
    src = textwrap.dedent(
        r"""
        int f(a)
        int a;
        int a;
        {
            return a;
        }
        """
    ).lstrip()
    res = _compile(tmp_path, src)
    assert not res.success
