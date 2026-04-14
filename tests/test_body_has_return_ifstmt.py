"""Test that _body_has_return correctly handles IfStmt."""
from pycc.compiler import Compiler


def test_wall_no_crash_on_if_return(tmp_path):
    """-Wall should not crash when checking if/else return paths."""
    code = r"""
int f(int x) {
    if (x > 0) return 1;
    else return 0;
}
int main(void) { return f(1) == 1 ? 0 : 1; }
"""
    c = tmp_path / "t.c"
    c.write_text(code)
    res = Compiler(optimize=False, wall=True).compile_file(str(c), str(tmp_path / "t"))
    assert res.success
    assert not any("control reaches end" in w for w in res.warnings or [])


def test_wall_warns_missing_return_with_if(tmp_path):
    """Function with if but no else should warn about missing return."""
    code = r"""
int f(int x) {
    if (x > 0) return 1;
}
int main(void) { return 0; }
"""
    c = tmp_path / "t.c"
    c.write_text(code)
    res = Compiler(optimize=False, wall=True).compile_file(str(c), str(tmp_path / "t"))
    assert res.success
    assert any("control reaches end" in w for w in res.warnings or [])
