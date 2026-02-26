import pytest

from pycc.compiler import Compiler


def test_void_variable_is_error(tmp_path):
    # C89: objects cannot have type void.
    code = r'''
void x;
int main(){ return 0; }
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success


def test_void_parameter_is_error(tmp_path):
    # C89: parameter of type void is invalid (except 'void' as sole parameter list).
    code = r'''
int f(void x){ return 0; }
int main(){ return f(0); }
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success


def test_void_only_parameter_list_ok(tmp_path):
    # `int f(void)` means no parameters.
    code = r'''
int f(void){ return 42; }
int main(){ return f(); }
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success
