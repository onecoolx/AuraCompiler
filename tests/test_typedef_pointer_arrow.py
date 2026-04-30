"""Tests for typedef pointer types used with -> and . operators.

Validates that semantic analysis correctly resolves typedef pointer types
when checking member access operators, and that the parser correctly
distinguishes function-returning-pointer from function-pointer-variable
when the function name is parenthesized.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pycc.compiler import Compiler
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer


def _parse_and_analyze(code: str):
    """Parse and run semantic analysis, return (ast, errors, warnings)."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    sema = SemanticAnalyzer()
    try:
        sema.analyze(ast)
    except Exception:
        pass
    return ast, sema.errors, sema.warnings


def _compile_and_run(tmp_path: Path, code: str) -> str:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run(
        [str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=10,
    )
    assert p.returncode == 0, f"runtime error (rc={p.returncode}): {p.stderr}"
    return p.stdout.strip()


# --- typedef pointer + -> ---

class TestTypedefPointerArrow:
    """typedef pointer types should be recognized as pointers for -> access."""

    def test_typedef_struct_pointer_arrow_no_error(self):
        code = '''
struct TValue { int tt_; int value_; };
typedef struct TValue *StkId;
void test(StkId o) { int x = o->tt_; }
int main(void) { return 0; }
'''
        _, errors, _ = _parse_and_analyze(code)
        assert not errors, f"unexpected errors: {errors}"

    def test_typedef_struct_pointer_dot_reports_error(self):
        code = '''
struct TValue { int tt_; };
typedef struct TValue *StkId;
void test(StkId o) { int x = o.tt_; }
int main(void) { return 0; }
'''
        _, errors, _ = _parse_and_analyze(code)
        assert any("'.' used on pointer" in e for e in errors)

    def test_chained_typedef_pointer_arrow(self):
        """typedef chain: typedef T *A; typedef A B; B->member should work."""
        code = '''
struct S { int x; };
typedef struct S *Sptr;
typedef Sptr Salias;
void test(Salias p) { int v = p->x; }
int main(void) { return 0; }
'''
        _, errors, _ = _parse_and_analyze(code)
        assert not errors, f"unexpected errors: {errors}"

    def test_direct_pointer_still_works(self):
        """Direct struct pointer (not typedef) should still work with ->."""
        code = '''
struct S { int x; };
void test(struct S *p) { int v = p->x; }
int main(void) { return 0; }
'''
        _, errors, _ = _parse_and_analyze(code)
        assert not errors, f"unexpected errors: {errors}"

    def test_non_pointer_arrow_still_rejected(self):
        """Non-pointer, non-typedef variable should still be rejected for ->."""
        code = '''
struct S { int x; };
void test(struct S s) { int v = s->x; }
int main(void) { return 0; }
'''
        _, errors, _ = _parse_and_analyze(code)
        assert any("'->' used on non-pointer" in e for e in errors)


# --- function returning pointer with parenthesized name ---

class TestParenFuncReturningPointer:
    """const char *(func)(params) should be parsed as a function, not a variable."""

    def test_paren_func_returning_pointer_is_function_decl(self):
        code = 'extern const char *(lua_typename)(int *L, int tp);'
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()
        from pycc.ast_nodes import FunctionDecl
        assert any(
            isinstance(d, FunctionDecl) and d.name == "lua_typename"
            for d in ast.declarations
        ), "expected FunctionDecl for lua_typename"

    def test_paren_func_returning_pointer_prototype_plus_definition(self):
        code = '''
extern const char *(lua_typename)(int *L, int tp);
const char *lua_typename(int *L, int t) { return 0; }
int main(void) { return 0; }
'''
        _, errors, _ = _parse_and_analyze(code)
        dup_errors = [e for e in errors if "Duplicate" in e]
        assert not dup_errors, f"unexpected duplicate errors: {dup_errors}"

    def test_fnptr_variable_still_parsed_as_declaration(self):
        """int (*fp)(int) should still be a variable Declaration, not FunctionDecl."""
        code = 'int (*fp)(int);'
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()
        from pycc.ast_nodes import Declaration
        assert any(
            isinstance(d, Declaration) and d.name == "fp"
            for d in ast.declarations
        ), "expected Declaration for fp"

    def test_paren_func_returning_pointer_compile_run(self, tmp_path: Path):
        code = (
            'extern int printf(const char *, ...);\n'
            'const char *(get_msg)(int id) {\n'
            '    if (id == 1) return "hello";\n'
            '    return "world";\n'
            '}\n'
            'int main(void) {\n'
            '    printf("%s %s\\n", get_msg(1), get_msg(2));\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "hello world"
