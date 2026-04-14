import os
import tempfile

from pycc.preprocessor import Preprocessor


def _pp(tmp_path, text: str, *, include_paths=None, filename: str = "t.c"):
    pp = Preprocessor(include_paths=include_paths or [])
    path = os.path.join(str(tmp_path), filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    res = pp.preprocess(path)
    assert res.errors == [], res.errors
    return res.text


def test_include_operand_expands_object_like_header_name_angle(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "foo.h").write_text("#define FOO_FROM_HEADER 123\n", encoding="utf-8")

    src = """
#define H <foo.h>
#include H
int x = FOO_FROM_HEADER;
""".lstrip()

    out = _pp(tmp_path, src, include_paths=[str(inc)])
    assert "int x" in out


def test_include_operand_expands_to_quoted_header_name(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "bar.h").write_text("#define BAR_FROM_HEADER 7\n", encoding="utf-8")

    src = """
#define H \"bar.h\"
#include H
int y = BAR_FROM_HEADER;
""".lstrip()

    out = _pp(tmp_path, src, include_paths=[str(inc)])
    assert "int y" in out


def test_include_operand_macro_must_expand_to_header_name(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()

    src = """
#define H 123
#include H
""".lstrip()

    pp = Preprocessor(include_paths=[str(inc)])
    path = os.path.join(str(tmp_path), "t.c")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    res = pp.preprocess(path)
    assert res.errors, "expected an error"
    assert "t.c:2:" in res.errors[0], res.errors[0]
