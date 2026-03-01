import os

from pycc.preprocessor import Preprocessor


def test_preprocessor_if_numeric_suffix_and_fn_like_macro(tmp_path):
    # System headers commonly use:
    #   - integer constants with suffixes: 201710L, 1U, etc.
    #   - function-like macro calls in #if: __GNUC_PREREQ(4,1)
    # Our built-in preprocessor should tolerate these forms.
    src = tmp_path / "t.c"
    src.write_text(
        """
#if __GNUC_PREREQ(4,1)
int a = 1;
#else
int a = 2;
#endif

#if 201710L > 0
int b = 3;
#else
int b = 4;
#endif
""".lstrip(),
        encoding="utf-8",
    )

    pp = Preprocessor(include_paths=[])
    res = pp.preprocess(str(src), initial_macros={})
    assert res.success, res.errors

    # Function-like macro calls in #if are tolerated (treated as 0 by default).
    assert "int a = 2;" in res.text
    assert "int a = 1;" not in res.text
    assert "int b = 3;" in res.text
    assert "int b = 4;" not in res.text
