import textwrap

import pytest

from pycc.preprocessor import Preprocessor


def _pp(tmp_path, source_text, *, include_paths=()):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(p) for p in include_paths])
    return pp.preprocess(str(src)).text


def test_include_quotes_prefers_current_dir_over_I(tmp_path):
    inc_dir = tmp_path / "inc"
    inc_dir.mkdir()

    # Same header name exists in both current dir and -I path.
    (tmp_path / "x.h").write_text("int from_current_dir;\n", encoding="utf-8")
    (inc_dir / "x.h").write_text("int from_I_path;\n", encoding="utf-8")

    out = _pp(
        tmp_path,
        """
        #include \"x.h\"
        """,
        include_paths=(inc_dir,),
    )

    assert "from_current_dir" in out
    assert "from_I_path" not in out


def test_include_angle_prefers_I_over_current_dir(tmp_path):
    inc_dir = tmp_path / "inc"
    inc_dir.mkdir()

    # Same header name exists in both current dir and -I path.
    (tmp_path / "x.h").write_text("int from_current_dir;\n", encoding="utf-8")
    (inc_dir / "x.h").write_text("int from_I_path;\n", encoding="utf-8")

    out = _pp(
        tmp_path,
        """
        #include <x.h>
        """,
        include_paths=(inc_dir,),
    )

    assert "from_I_path" in out
    assert "from_current_dir" not in out
