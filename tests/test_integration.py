"""Integration tests.

Note: this file mostly contains lexer integration tests.
The end-to-end compile+run tests live in other modules.
"""

import pytest
from pycc.lexer import Lexer, TokenType
from pycc.ast_nodes import *


class TestLexerIntegration:
    """Integration tests for lexer with various C programs"""
    
    def test_simple_function_lexing(self):
        """Test lexing a simple function"""
        code = """
        int add(int a, int b) {
            return a + b;
        }
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
        assert tokens[-1].type == TokenType.EOF
        
        # Verify key tokens are present
        token_types = [t.type for t in tokens]
        assert TokenType.KEYWORD in token_types
        assert TokenType.IDENTIFIER in token_types
        assert TokenType.LPAREN in token_types
        assert TokenType.RPAREN in token_types
        assert TokenType.LBRACE in token_types
        assert TokenType.RBRACE in token_types
        assert TokenType.SEMICOLON in token_types
    
    def test_struct_lexing(self):
        """Test lexing struct definition"""
        code = """
        struct Point {
            int x;
            int y;
        };
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
    
    def test_array_operations(self):
        """Test lexing array operations"""
        code = """
        int arr[10];
        arr[0] = 5;
        int x = arr[0];
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
        
        # Check for array-related tokens
        token_types = [t.type for t in tokens]
        assert TokenType.LBRACKET in token_types
        assert TokenType.RBRACKET in token_types
    
    def test_pointer_operations(self):
        """Test lexing pointer operations"""
        code = """
        int *ptr;
        ptr = &x;
        int y = *ptr;
        ptr->field;
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
        
        token_types = [t.type for t in tokens]
        assert TokenType.STAR in token_types
        assert TokenType.AMPERSAND in token_types
        assert TokenType.ARROW in token_types
    
    def test_all_control_structures(self):
        """Test lexing all control structures"""
        code = """
        if (x > 0) {
            y = 1;
        } else {
            y = 2;
        }
        
        while (x < 10) {
            x = x + 1;
        }
        
        for (int i = 0; i < 10; i++) {
            sum = sum + i;
        }
        
        do {
            x = x - 1;
        } while (x > 0);
        
        switch (x) {
            case 1:
                y = 10;
                break;
            case 2:
                y = 20;
                break;
            default:
                y = 0;
        }
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
    
    def test_complex_expressions(self):
        """Test lexing complex expressions"""
        code = """
        int result = (a + b) * (c - d) / e;
        int flag = (x > 5) && (y < 10) || (z == 0);
        int bit = a & b | c ^ d;
        int shifted = x << 2;
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()


class TestFactorialProgram:
    """Test lexing factorial example"""
    
    def test_factorial_example(self):
        """Test full factorial program"""
        with open("examples/factorial.c", "r") as f:
            code = f.read()
        
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()


def test_global_var_read_write(tmp_path):
    from pycc.compiler import Compiler
    import subprocess

    # Minimal global variable support: .comm + RIP-relative load/store
    src = tmp_path / "g.c"
    src.write_text(
        """
int g;
int main(){
    g = 41;
    g = g + 1;
    return g;
}
""".lstrip()
    )
    out = tmp_path / "g"
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(out))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    r = subprocess.run([str(out)], capture_output=True, text=True)
    assert r.returncode == 42


def test_global_int_initializer(tmp_path):
    from pycc.compiler import Compiler
    import subprocess

    src = tmp_path / "gi.c"
    src.write_text(
        """
int g = 42;
int main(){ return g; }
""".lstrip()
    )
    out = tmp_path / "gi"
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(out))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    r = subprocess.run([str(out)], capture_output=True, text=True)
    assert r.returncode == 42


def test_global_char_initializer(tmp_path):
    from pycc.compiler import Compiler
    import subprocess

    src = tmp_path / "gc.c"
    src.write_text(
        """
char c = 40;
int main(){ return c + 2; }
""".lstrip()
    )
    out = tmp_path / "gc"
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(out))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    r = subprocess.run([str(out)], capture_output=True, text=True)
    assert r.returncode == 42


def test_static_global_initializer(tmp_path):
    from pycc.compiler import Compiler
    import subprocess

    src = tmp_path / "sg.c"
    src.write_text(
        """
static int g = 42;
int main(){ return g; }
""".lstrip()
    )
    out = tmp_path / "sg"
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(out))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    r = subprocess.run([str(out)], capture_output=True, text=True)
    assert r.returncode == 42


def test_extern_global_declaration_then_definition(tmp_path):
    from pycc.compiler import Compiler
    import subprocess

    src = tmp_path / "eg.c"
    src.write_text(
        """
extern int g;
int g = 41;
int main(){ return g + 1; }
""".lstrip()
    )
    out = tmp_path / "eg"
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(out))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    r = subprocess.run([str(out)], capture_output=True, text=True)
    assert r.returncode == 42


def test_extern_function_prototype_and_call(tmp_path):
    from pycc.compiler import Compiler
    import subprocess

    src = tmp_path / "ef.c"
    src.write_text(
        """
extern int add(int a, int b);
int add(int a, int b){ return a + b; }
int main(){ return add(40, 2); }
""".lstrip()
    )
    out = tmp_path / "ef"
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(out))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    r = subprocess.run([str(out)], capture_output=True, text=True)
    assert r.returncode == 42


def test_global_string_pointer_initializer(tmp_path):
        from pycc.compiler import Compiler
        import subprocess

        src = tmp_path / "gs.c"
        src.write_text(
                """
char *s = "hi";
int main(){
    return s[0] + s[1];
}
""".lstrip()
        )
        out = tmp_path / "gs"
        comp = Compiler(optimize=False)
        res = comp.compile_file(str(src), str(out))
        assert res.success, "compile failed: " + "\n".join(res.errors)
        r = subprocess.run([str(out)], capture_output=True, text=True)
        assert r.returncode == (ord('h') + ord('i'))


class TestTokenization:
    """Test tokenization of various C99 features"""
    
    def test_c99_keywords(self):
        """Test C99-specific keywords"""
        keywords = "_Bool _Complex _Imaginary inline restrict volatile"
        lexer = Lexer(keywords)
        tokens = lexer.tokenize()
        
        token_types = [t.type for t in tokens[:-1]]  # Exclude EOF
        assert all(t == TokenType.KEYWORD for t in token_types)
    
    def test_variable_length_arrays(self):
        """Test VLA syntax"""
        code = """
        int n = 5;
        int arr[n];
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
    
    def test_designated_initializers(self):
        """Test designated initializer syntax"""
        code = """
        struct Point p = {.x = 1, .y = 2};
        int arr[] = {[0] = 10, [5] = 20};
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
    
    def test_compound_literals(self):
        """Test compound literal syntax"""
        code = """
        struct Point p = (struct Point){1, 2};
        int *ptr = (int[]){1, 2, 3, 4, 5};
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()


class TestEdgeCasesIntegration:
    """Integration test for edge cases"""
    
    def test_long_identifiers(self):
        """Test very long identifier"""
        long_id = "a" * 1000
        code = f"{long_id} = 5;"
        
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == long_id
    
    def test_many_operators(self):
        """Test expression with many operators"""
        code = "x = a + b - c * d / e % f << g >> h & i | j ^ k && l || m;"
        
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
    
    def test_nested_structures(self):
        """Test deeply nested structures"""
        code = """
        int main() {
            {
                {
                    {
                        int x = 5;
                    }
                }
            }
        }
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()
    
    def test_string_with_escape_sequences(self):
        """Test strings with various escape sequences"""
        code = r'''
        char *s1 = "hello\nworld";
        char *s2 = "tab\there";
        char *s3 = "quote\"here";
        char *s4 = "backslash\\here";
        '''
        
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        
        assert not lexer.has_errors()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
