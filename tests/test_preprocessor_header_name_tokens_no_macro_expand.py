import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_macros_not_expanded_inside_header_name_tokens(tmp_path):
    # Even if a macro shares a name with part of a header-name, it must not
    # be expanded *inside* the "..." or <...> header-name token.
    (tmp_path / "A.h").write_text("#define Z 9\n", encoding="utf-8")

    out = _pp_text(
        tmp_path,
        """
        #define A 123
        #include "A.h"
        int z = Z;
        """,
    )

    assert "int z = 9;" in out
