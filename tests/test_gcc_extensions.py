"""Unit tests for the GCC extension stripper.

Tests specific examples and edge cases for strip_gcc_extensions().

Requirements: 3.1, 3.3, 3.7, 3.8
"""
from __future__ import annotations

from pycc.gcc_extensions import strip_gcc_extensions


# ---------------------------------------------------------------------------
# Requirement 3.1: __attribute__((anything)) removal
# ---------------------------------------------------------------------------

class TestAttributeRemoval:
    """Test __attribute__((...)) removal with various forms."""

    def test_attribute_unused(self):
        """Simple __attribute__((unused)) is removed."""
        text = "int x __attribute__((unused));"
        result = strip_gcc_extensions(text)
        assert "__attribute__" not in result
        assert "int x" in result
        assert result.strip().endswith(";")

    def test_attribute_format_printf(self):
        """__attribute__((format(printf, 1, 2))) with nested parens is removed."""
        text = "void log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));"
        result = strip_gcc_extensions(text)
        assert "__attribute__" not in result
        assert "void log(const char *fmt, ...)" in result
        assert result.strip().endswith(";")

    def test_attribute_with_whitespace(self):
        """__attribute__ with whitespace before parens is removed."""
        text = "int x __attribute__  ((unused));"
        result = strip_gcc_extensions(text)
        assert "__attribute__" not in result
        assert "int x" in result

    def test_multiple_attributes(self):
        """Multiple __attribute__ annotations in one text are all removed."""
        text = "int x __attribute__((unused)); int y __attribute__((aligned(4)));"
        result = strip_gcc_extensions(text)
        assert "__attribute__" not in result
        assert "int x" in result
        assert "int y" in result

    def test_attribute_noreturn(self):
        """__attribute__((noreturn)) is removed."""
        text = "void exit(int) __attribute__((noreturn));"
        result = strip_gcc_extensions(text)
        assert "__attribute__" not in result
        assert "void exit(int)" in result


# ---------------------------------------------------------------------------
# Requirement 3.7: Deep nesting (3+ levels)
# ---------------------------------------------------------------------------

class TestDeepNesting:
    """Test deeply nested __attribute__ parentheses."""

    def test_nonnull_deep_nesting(self):
        """__attribute__(((__nonnull__(1, 2)))) with 3 levels of parens."""
        text = "void f(char *a, char *b) __attribute__(((__nonnull__(1, 2))));"
        result = strip_gcc_extensions(text)
        assert "__attribute__" not in result
        assert "__nonnull__" not in result
        assert "void f(char *a, char *b)" in result
        assert result.strip().endswith(";")

    def test_four_level_nesting(self):
        """4 levels of nested parentheses inside __attribute__."""
        text = "int x __attribute__((((deep))));"
        result = strip_gcc_extensions(text)
        assert "__attribute__" not in result
        assert "int x" in result

    def test_mixed_nesting_with_commas(self):
        """Nested parens with commas inside __attribute__."""
        text = "void f(void) __attribute__((format(printf, 1, 2), noreturn));"
        result = strip_gcc_extensions(text)
        assert "__attribute__" not in result
        assert "void f(void)" in result


# ---------------------------------------------------------------------------
# Requirement 3.3: __asm__ removal
# ---------------------------------------------------------------------------

class TestAsmRemoval:
    """Test __asm__(...) and __asm__ volatile(...) removal."""

    def test_asm_nop(self):
        """__asm__("nop") is removed."""
        text = '__asm__("nop");'
        result = strip_gcc_extensions(text)
        assert "__asm__" not in result
        assert "nop" not in result

    def test_asm_volatile_memory_barrier(self):
        """__asm__ volatile("" ::: "memory") is removed."""
        text = '__asm__ volatile("" ::: "memory");'
        result = strip_gcc_extensions(text)
        assert "__asm__" not in result
        assert "volatile" not in result
        assert "memory" not in result

    def test_asm_with_surrounding_code(self):
        """__asm__ in context preserves surrounding code."""
        text = 'int x = 1; __asm__("nop"); int y = 2;'
        result = strip_gcc_extensions(text)
        assert "__asm__" not in result
        assert "int x = 1;" in result
        assert "int y = 2;" in result

    def test_asm_volatile_with_whitespace(self):
        """__asm__ volatile with extra whitespace."""
        text = '__asm__   volatile  ("cli");'
        result = strip_gcc_extensions(text)
        assert "__asm__" not in result


# ---------------------------------------------------------------------------
# Requirement 3.8: String literal protection
# ---------------------------------------------------------------------------

class TestStringLiteralProtection:
    """Test that GCC-like keywords inside string literals are not modified."""

    def test_attribute_in_string(self):
        """__attribute__ inside a string literal is preserved."""
        text = 'const char *s = "__attribute__((unused))";'
        result = strip_gcc_extensions(text)
        assert '"__attribute__((unused))"' in result

    def test_asm_in_string(self):
        """__asm__ inside a string literal is preserved."""
        text = 'const char *s = "__asm__(nop)";'
        result = strip_gcc_extensions(text)
        assert '"__asm__(nop)"' in result

    def test_extension_in_string(self):
        """__extension__ inside a string literal is preserved."""
        text = 'const char *msg = "use __extension__ here";'
        result = strip_gcc_extensions(text)
        assert '"use __extension__ here"' in result

    def test_float_type_in_string(self):
        """_Float128 inside a string literal is preserved."""
        text = 'const char *t = "_Float128 is a GCC type";'
        result = strip_gcc_extensions(text)
        assert '"_Float128 is a GCC type"' in result

    def test_mixed_real_and_string_extensions(self):
        """Real extension is removed but string content is preserved."""
        text = '__extension__ const char *s = "__extension__";'
        result = strip_gcc_extensions(text)
        # Real __extension__ keyword removed
        assert result.strip().startswith("const char") or result.strip().startswith(" const char")
        # String content preserved
        assert '"__extension__"' in result


# ---------------------------------------------------------------------------
# Edge cases: empty and no-extension input
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test empty input and input without any GCC extensions."""

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert strip_gcc_extensions("") == ""

    def test_no_extensions(self):
        """Plain C code without extensions is returned unchanged."""
        text = "int main(void) { return 0; }"
        assert strip_gcc_extensions(text) == text

    def test_whitespace_only(self):
        """Whitespace-only input is returned unchanged."""
        text = "   \n\t  \n"
        assert strip_gcc_extensions(text) == text

    def test_normal_c_with_underscores(self):
        """C code with underscores that aren't GCC extensions is unchanged."""
        text = "int my_var = _other_var + __count;"
        assert strip_gcc_extensions(text) == text

    def test_simple_keywords_removal(self):
        """Simple keywords like __extension__, __inline, __restrict are removed."""
        text = "__extension__ typedef __inline int myint;"
        result = strip_gcc_extensions(text)
        assert "__extension__" not in result
        assert "__inline" not in result
        assert "typedef" in result
        assert "int myint;" in result

    def test_float_type_replacement(self):
        """_Float128 is replaced with long double."""
        text = "_Float128 x = 1.0;"
        result = strip_gcc_extensions(text)
        assert "_Float128" not in result
        assert "long double" in result
        assert "x = 1.0;" in result

    def test_malformed_attribute_preserved(self):
        """__attribute__ without proper (( is left unchanged."""
        text = "int x __attribute__(unused);"
        result = strip_gcc_extensions(text)
        # Only single paren - malformed, should be preserved
        assert "__attribute__" in result
