import pytest

from pycc.compiler import Compiler


def test_pointer_minus_pointer_different_base_types_rejected(tmp_path):
    # In standard C, pointer subtraction is only defined for pointers into the
    # same array object, and the types should be compatible.
    # Our subset should reject obviously mismatched base types.
    code = r'''
int main(){
    int a[2];
    char b[2];
    int *p = a;
    char *q = b;
    return (int)(p - q);
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
    assert any("pointer" in e.lower() and "-" in e for e in res.errors)
