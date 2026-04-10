"""Tests for #if integer width, overflow, and suffix semantics (Task 10.1).

Covers Requirements 12.1, 12.2:
- Consistent overflow handling (Python arbitrary precision)
- Correct parsing of integer suffixes (1L, 2UL, 3U, etc.)
"""
import textwrap
from pathlib import Path

from pycc.preprocessor import Preprocessor


def _pp(tmp_path, code: str) -> str:
    src = tmp_path / "t.c"
    src.write_text(textwrap.dedent(code).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


# ---------------------------------------------------------------------------
# Integer suffix parsing (Requirement 12.2)
# ---------------------------------------------------------------------------

class TestIfIntegerSuffixes:
    """Tests for #if integer literal suffix parsing."""

    def test_suffix_L(self, tmp_path):
        """1L should be parsed as integer 1."""
        out = _pp(tmp_path, """
            #if 1L
            yes
            #endif
        """)
        assert "yes" in out

    def test_suffix_UL(self, tmp_path):
        """2UL should be parsed as integer 2."""
        out = _pp(tmp_path, """
            #if 2UL == 2
            yes
            #endif
        """)
        assert "yes" in out

    def test_suffix_U(self, tmp_path):
        """3U should be parsed as integer 3."""
        out = _pp(tmp_path, """
            #if 3U == 3
            yes
            #endif
        """)
        assert "yes" in out

    def test_suffix_LL(self, tmp_path):
        """4LL should be parsed as integer 4."""
        out = _pp(tmp_path, """
            #if 4LL == 4
            yes
            #endif
        """)
        assert "yes" in out

    def test_suffix_ULL(self, tmp_path):
        """5ULL should be parsed as integer 5."""
        out = _pp(tmp_path, """
            #if 5ULL == 5
            yes
            #endif
        """)
        assert "yes" in out

    def test_suffix_lowercase_l(self, tmp_path):
        """1l should be parsed as integer 1."""
        out = _pp(tmp_path, """
            #if 1l == 1
            yes
            #endif
        """)
        assert "yes" in out

    def test_suffix_lowercase_ul(self, tmp_path):
        """2ul should be parsed as integer 2."""
        out = _pp(tmp_path, """
            #if 2ul == 2
            yes
            #endif
        """)
        assert "yes" in out

    def test_hex_with_suffix(self, tmp_path):
        """0xFFU should be parsed as 255."""
        out = _pp(tmp_path, """
            #if 0xFFU == 255
            yes
            #endif
        """)
        assert "yes" in out

    def test_hex_with_UL_suffix(self, tmp_path):
        """0x10UL should be parsed as 16."""
        out = _pp(tmp_path, """
            #if 0x10UL == 16
            yes
            #endif
        """)
        assert "yes" in out


# ---------------------------------------------------------------------------
# Overflow handling (Requirement 12.1)
# ---------------------------------------------------------------------------

class TestIfOverflowHandling:
    """Tests for #if integer overflow behavior (Python arbitrary precision)."""

    def test_large_value_no_overflow(self, tmp_path):
        """Large values should not overflow (Python arbitrary precision)."""
        out = _pp(tmp_path, """
            #if 2147483647 + 1 > 0
            yes
            #endif
        """)
        assert "yes" in out

    def test_large_multiplication(self, tmp_path):
        """Large multiplication should work correctly."""
        out = _pp(tmp_path, """
            #if 1000000 * 1000000 == 1000000000000
            yes
            #endif
        """)
        assert "yes" in out

    def test_negative_values(self, tmp_path):
        """Negative values should work correctly."""
        out = _pp(tmp_path, """
            #if -1 < 0
            yes
            #endif
        """)
        assert "yes" in out

    def test_shift_large(self, tmp_path):
        """Large shift should work correctly."""
        out = _pp(tmp_path, """
            #if 1 << 31 == 2147483648
            yes
            #endif
        """)
        assert "yes" in out

    def test_consistent_evaluation(self, tmp_path):
        """Same expression in different contexts should produce same result."""
        out = _pp(tmp_path, """
            #if 100 + 200 == 300
            first
            #endif
            #if 100 + 200 == 300
            second
            #endif
        """)
        assert "first" in out
        assert "second" in out

    def test_zero_division_error(self, tmp_path):
        """Division by zero should be handled (not crash)."""
        # This may raise an error or evaluate to 0 depending on implementation
        try:
            out = _pp(tmp_path, """
                #if 1 / 0
                yes
                #else
                no
                #endif
            """)
            # If it doesn't crash, that's acceptable
        except RuntimeError:
            pass  # Also acceptable
