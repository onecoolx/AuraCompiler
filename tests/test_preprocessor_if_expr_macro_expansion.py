from pathlib import Path

from pycc.compiler import Compiler


def _run_E(tmp_path: Path, code: str):
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler()
    # -E: run built-in preprocessor and print output
    return comp.compile_file(str(c_path), None, preprocess_only=True)


def test_E_if_expr_expands_object_like_macros(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define A 1
#define B 2
#if A + B == 3
int ok = 1;
#else
int ok = 0;
#endif
""".lstrip(),
    )
    assert res.success, res.errors
    assert "int ok = 1;" in res.assembly
    assert "int ok = 0;" not in res.assembly


def test_E_if_expr_does_not_expand_defined_argument(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define X Y
#define Y 1
#if defined(X)
int ok = 1;
#else
int ok = 0;
#endif
""".lstrip(),
    )
    assert res.success, res.errors
    assert "int ok = 1;" in res.assembly
    assert "int ok = 0;" not in res.assembly
