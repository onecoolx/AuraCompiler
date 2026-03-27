import pytest

from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_enum_enumerator_value_must_be_ice(tmp_path):
    code = r"""
int x = 3;

enum E {
  A = x,
  B = 2
};

int main() { return B; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
