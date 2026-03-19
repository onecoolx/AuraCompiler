import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_object_like_macro_name_not_reexpanded_within_its_own_replacement_list(tmp_path):
    # A classic hide-set behavior subset: during the rescan of A's replacement
    # list, the macro name A should be disabled to prevent runaway growth.
    out = _pp_text(
        tmp_path,
        """
        #define A A + 1
        int x = A;
        """,
    )

    # One-step expansion is OK; it must not keep expanding infinitely.
    assert "int x = A + 1;" in out
