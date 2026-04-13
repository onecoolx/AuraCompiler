"""Tests for the -Wall/-Werror warning system."""
from pycc.compiler import Compiler


def _compile(tmp_path, code, wall=False, werror=False):
    c = tmp_path / "t.c"
    o = tmp_path / "t"
    c.write_text(code)
    comp = Compiler(optimize=False, wall=wall, werror=werror)
    return comp.compile_file(str(c), str(o))


def test_wall_missing_return_warns(tmp_path):
    code = "int f(void) { int x = 1; }\nint main(void) { return 0; }\n"
    res = _compile(tmp_path, code, wall=True)
    assert res.success
    assert any("control reaches end of non-void" in w for w in res.warnings)


def test_no_wall_no_missing_return_warning(tmp_path):
    code = "int f(void) { int x = 1; }\nint main(void) { return 0; }\n"
    res = _compile(tmp_path, code, wall=False)
    assert res.success
    assert not any("control reaches end of non-void" in w for w in (res.warnings or []))


def test_werror_turns_warnings_into_errors(tmp_path):
    code = "int f(void) { int x = 1; }\nint main(void) { return 0; }\n"
    res = _compile(tmp_path, code, wall=True, werror=True)
    assert not res.success
    assert any("Werror" in e for e in res.errors)


def test_wall_implicit_function_decl_warns(tmp_path):
    """Implicit function declaration produces a warning (always, even without -Wall)."""
    code = "int unknown_func(void);\nint main(void) { return unknown_func(); }\n"
    res = _compile(tmp_path, code, wall=True)
    # The function is declared but not defined — link may fail, but
    # the implicit-decl warning is for truly undeclared functions.
    # Use a case where the function IS defined elsewhere (or just check
    # that the warning infrastructure works for the always-on case).
    # For now, test with a function that's called without prior declaration
    # but defined later in the same TU.
    code2 = "int main(void) { return helper(); }\nint helper(void) { return 0; }\n"
    res2 = _compile(tmp_path, code2, wall=True)
    assert any("implicit declaration" in w for w in (res2.warnings or []))


def test_wall_void_function_no_warning(tmp_path):
    code = "void f(void) { }\nint main(void) { return 0; }\n"
    res = _compile(tmp_path, code, wall=True)
    assert not any("control reaches end" in w for w in (res.warnings or []))


def test_wall_function_with_return_no_warning(tmp_path):
    code = "int f(void) { return 42; }\nint main(void) { return 0; }\n"
    res = _compile(tmp_path, code, wall=True)
    assert not any("control reaches end" in w for w in (res.warnings or []))
