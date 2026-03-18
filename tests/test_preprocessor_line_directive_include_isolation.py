import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text, *, include_paths=()):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(p) for p in include_paths])
    return pp.preprocess(str(src)).text


def test_line_directive_does_not_leak_across_includes(tmp_path):
    (tmp_path / "a.h").write_text(
        textwrap.dedent(
            r"""
            #line 10 "virtual_a.h"
            const char *a_file = __FILE__;
            int a_line = __LINE__;

            #include "b.h"
            """
        ).lstrip(),
        encoding="utf-8",
    )

    (tmp_path / "b.h").write_text(
        textwrap.dedent(
            r"""
            const char *b_file = __FILE__;
            int b_line = __LINE__;
            """
        ).lstrip(),
        encoding="utf-8",
    )

    out = _pp_text(
        tmp_path,
        r"""
        #include "a.h"
        """,
    )

    # a.h has a virtual filename due to #line.
    assert '"virtual_a.h"' in out

    # b.h should use its own logical filename (defaults to basename), not leak virtual_a.h.
    assert '"b.h"' in out
