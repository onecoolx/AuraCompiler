"""Property tests: ICE evaluation correctness (Property 12)."""
import pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_ice_enum_arithmetic(tmp_path):
    """Enum values computed from arithmetic ICE."""
    code = """
enum { A = 1 + 2, B = A * 3, C = B - A };
int main(void) { return C; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success


def test_ice_sizeof_type_in_enum(tmp_path):
    """sizeof(type-name) is valid in ICE context."""
    code = """
enum { SZ = sizeof(int) };
int main(void) { return SZ; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success


def test_ice_ternary_in_enum(tmp_path):
    """Ternary operator in ICE."""
    code = """
enum { V = (1 > 0) ? 42 : 0 };
int main(void) { return V; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success


def test_ice_bitwise_in_switch_case(tmp_path):
    """Bitwise operations in switch/case ICE."""
    code = """
int main(void) {
    int x = 3;
    switch (x) {
        case (1 << 1) | 1: return 1;
        default: return 0;
    }
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success
