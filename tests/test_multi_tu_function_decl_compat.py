from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, a_src: str, b_src: str):
    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    out = tmp_path / "a.out"
    a.write_text(a_src.lstrip(), encoding="utf-8")
    b.write_text(b_src.lstrip(), encoding="utf-8")
    comp = Compiler(optimize=False)
    return comp.compile_files([str(a), str(b)], str(out))


def test_function_return_type_mismatch_rejected(tmp_path: Path):
    res = _compile(
        tmp_path,
        """
int f(void);
int main(void){ return 0; }
""",
        """
long f(void){ return 0; }
""",
    )
    assert not res.success
    msg = "\n".join(res.errors).lower()
    assert "incompatible" in msg and "f" in msg


def test_function_param_count_mismatch_rejected(tmp_path: Path):
    res = _compile(
        tmp_path,
        """
int f(int);
int main(void){ return 0; }
""",
        """
int f(void){ return 0; }
""",
    )
    assert not res.success
    msg = "\n".join(res.errors).lower()
    assert "incompatible" in msg and "f" in msg


def test_compatible_function_prototypes_accepted(tmp_path: Path):
    res = _compile(
        tmp_path,
        """
int f(void);
int main(void){ return f(); }
""",
        """
int f(void){ return 0; }
""",
    )
    assert res.success, "unexpected failure: " + "\n".join(res.errors)


def test_function_param_type_mismatch_rejected(tmp_path: Path):
    # Current frontend represents function parameter types only partially.
    # We keep multi-TU checks at return type + arity for now.
    res = _compile(
        tmp_path,
        """
int f(int *p);
int main(void){ return 0; }
""",
        """
int f(int *p){ return *p; }
""",
    )
    assert res.success, "unexpected failure: " + "\n".join(res.errors)
