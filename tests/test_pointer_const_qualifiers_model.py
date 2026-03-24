from __future__ import annotations

from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_assignment_through_pointer_to_const_is_rejected(tmp_path):
    # const int *p; *p = 1;  => non-modifiable lvalue
    src = r"""
int main(void) {
    const int x = 1;
    const int *p = &x;
    *p = 2;
    return 0;
}
"""
    res = _compile(tmp_path, src)
    assert not res.success


def test_assignment_to_const_pointer_is_rejected(tmp_path):
    # int *const p; p = &y;  => const pointer (cannot reassign)
    src = r"""
int main(void) {
    int x = 1;
    int y = 2;
    int *const p = &x;
    p = &y;
    return 0;
}
"""
    res = _compile(tmp_path, src)
    assert not res.success
