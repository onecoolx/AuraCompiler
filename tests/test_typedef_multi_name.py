"""Test: typedef with multiple names (typedef T *A, *B;)."""
from pycc.compiler import Compiler


def test_typedef_multi_name_pointer(tmp_path):
    """typedef struct _S *A, *B; should define both A and B as pointer types."""
    code = r"""
struct _S { int x; };
typedef struct _S *SA, *SB;
int main(void) {
    struct _S s;
    s.x = 42;
    SA a = &s;
    SB b = &s;
    return (*a).x == 42 ? 0 : 1;
}
"""
    c = tmp_path / "t.c"
    o = tmp_path / "t"
    c.write_text(code)
    res = Compiler(optimize=False).compile_file(str(c), str(o))
    assert res.success, "compile failed: " + "\n".join(res.errors)


def test_typedef_multi_name_plain(tmp_path):
    """typedef int A, B; should define both A and B as int."""
    code = r"""
typedef int myint1, myint2;
int main(void) {
    myint1 a = 10;
    myint2 b = 20;
    return a + b == 30 ? 0 : 1;
}
"""
    c = tmp_path / "t.c"
    o = tmp_path / "t"
    c.write_text(code)
    import subprocess
    res = Compiler(optimize=False).compile_file(str(c), str(o))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(o)], check=False, timeout=5)
    assert p.returncode == 0
