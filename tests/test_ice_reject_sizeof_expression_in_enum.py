import pytest

from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_ice_reject_sizeof_expression_in_enum(tmp_path):
    code = r"""
int x = 1;

enum E {
  A = (int)sizeof(x)
};

int main(void) { return 0; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
