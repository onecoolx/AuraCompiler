"""Property tests: declarator parsing roundtrip (Property 11)."""
import pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_function_pointer_declarator(tmp_path):
    code = "int add(int a, int b) { return a + b; }\nint main(void) { int (*fp)(int, int) = add; return fp(1, 2); }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_pointer_array_declarator(tmp_path):
    code = "int main(void) { int a; int *arr[1]; arr[0] = &a; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_array_pointer_declarator(tmp_path):
    code = "int main(void) { int a[3] = {1, 2, 3}; int (*p)[3] = &a; return (*p)[1]; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_function_pointer_array_declarator(tmp_path):
    code = """
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }
int main(void) {
    int (*ops[2])(int, int);
    ops[0] = add;
    ops[1] = sub;
    return ops[0](3, 1) + ops[1](5, 2);
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success
