import pytest

from pycc.compiler import Compiler


def test_conflicting_global_linkage_rejected(tmp_path):
    # In the same translation unit, `static` vs non-static of the same name is a conflict.
    code = """
static int g;
int g;
int main(){ return 0; }
""".lstrip()

    c_path = tmp_path / "conflict.c"
    out_path = tmp_path / "conflict"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
    assert any("conflicting linkage" in e for e in res.errors)
