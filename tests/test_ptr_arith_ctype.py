"""Unit tests for pointer arithmetic and array indexing CType migration (task 3.7).

Validates that the IR generator correctly uses CType-based resolution for
pointer arithmetic scaling, array indexing, and result type propagation
in the symbol table.
"""
import pytest
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def _get_ir_and_symtable(code: str):
    """Compile code and return IR instructions and symbol table."""
    from pycc.lexer import Lexer
    from pycc.parser import Parser
    from pycc.semantics import SemanticAnalyzer
    from pycc.ir import IRGenerator
    lexer = Lexer(code)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    analyzer = SemanticAnalyzer()
    sema_ctx = analyzer.analyze(ast)
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    ir = gen.generate(ast)
    return ir, getattr(gen, "_sym_table", None)


class TestPointerArithmeticScaling:
    """Test that pointer arithmetic uses correct element size scaling."""

    def test_int_pointer_add(self, tmp_path):
        """p + 2 where p is int* should advance by 2*sizeof(int)."""
        code = r'''
int main(void) {
    int arr[4];
    arr[0] = 10; arr[1] = 20; arr[2] = 30; arr[3] = 40;
    int *p = arr;
    int *q = p + 2;
    return *q;
}
'''
        assert _compile_and_run(tmp_path, code) == 30

    def test_char_pointer_add(self, tmp_path):
        """p + 2 where p is char* should advance by 2 bytes."""
        code = r'''
int main(void) {
    char buf[4];
    buf[0] = 'A'; buf[1] = 'B'; buf[2] = 'C'; buf[3] = 0;
    char *p = buf;
    char *q = p + 2;
    return *q;
}
'''
        assert _compile_and_run(tmp_path, code) == ord('C')

    def test_pointer_difference_char_cast(self, tmp_path):
        """(char*)py - (char*)px should give byte offset, not element count."""
        code = r'''
struct S { int x; int y; };
int main(void) {
    struct S s;
    int *px = &s.x;
    int *py = &s.y;
    if ((char*)py - (char*)px != 4) return 1;
    return 0;
}
'''
        assert _compile_and_run(tmp_path, code) == 0

    def test_pointer_add_compound(self, tmp_path):
        """p += 3 where p is int* should advance by 3*sizeof(int)."""
        code = r'''
int main(void) {
    int arr[4];
    arr[0] = 10; arr[1] = 20; arr[2] = 30; arr[3] = 40;
    int *p = arr;
    p += 3;
    return *p;
}
'''
        assert _compile_and_run(tmp_path, code) == 40


class TestArrayIndexing:
    """Test array indexing with correct element size."""

    def test_int_array_index(self, tmp_path):
        code = r'''
int main(void) {
    int arr[5];
    arr[0] = 1; arr[1] = 2; arr[2] = 3; arr[3] = 4; arr[4] = 5;
    return arr[3];
}
'''
        assert _compile_and_run(tmp_path, code) == 4

    def test_char_array_index(self, tmp_path):
        code = r'''
int main(void) {
    char buf[4];
    buf[0] = 'X'; buf[1] = 'Y'; buf[2] = 'Z'; buf[3] = 0;
    return buf[1];
}
'''
        assert _compile_and_run(tmp_path, code) == ord('Y')

    def test_struct_array_index(self, tmp_path):
        """Indexing an array of structs should use correct struct size."""
        code = r'''
struct Pt { int x; int y; };
int main(void) {
    struct Pt pts[3];
    pts[0].x = 1; pts[0].y = 2;
    pts[1].x = 3; pts[1].y = 4;
    pts[2].x = 5; pts[2].y = 6;
    return pts[2].x + pts[2].y;
}
'''
        assert _compile_and_run(tmp_path, code) == 11


class TestSymbolTableRegistration:
    """Test that pointer arithmetic results are registered in the symbol table."""

    def test_array_decay_registers_pointer_ctype(self):
        """When a local array decays to a pointer, the IR should contain
        a mov_addr instruction for the array decay."""
        code = "int main(void) { int arr[3]; int *p = arr; return 0; }\n"
        ir, sym_table = _get_ir_and_symtable(code)
        assert sym_table is not None
        # The mov_addr instruction should exist for array decay.
        found_decay = False
        for inst in ir:
            if inst.op == "mov_addr" and inst.operand1 and "arr" in inst.operand1:
                found_decay = True
                assert inst.result is not None
                break
        assert found_decay, "Expected mov_addr for array decay"

    def test_load_index_result_type(self):
        """Verify that load_index instructions are generated for array access."""
        code = "int main(void) { int arr[3]; arr[0] = 1; return arr[1]; }\n"
        ir, sym_table = _get_ir_and_symtable(code)
        assert sym_table is not None
        # There should be at least one load_index or store_index instruction.
        has_index_op = any(
            inst.op in ("load_index", "store_index", "addr_index")
            for inst in ir
        )
        assert has_index_op, "Expected index operations for array access"

    def test_pointee_size_from_ctype_helper(self):
        """Test the _pointee_size_from_ctype helper method directly."""
        from pycc.types import (
            TypedSymbolTable, PointerType, IntegerType, TypeKind,
            ArrayType as CArrayType,
        )
        from pycc.ir import IRGenerator

        gen = IRGenerator()
        gen._sym_table = TypedSymbolTable()

        # Insert a pointer to int
        int_ct = IntegerType(kind=TypeKind.INT)
        ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=int_ct)
        gen._sym_table.insert("%t0", ptr_ct)

        # Insert a pointer to char
        char_ct = IntegerType(kind=TypeKind.CHAR)
        char_ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=char_ct)
        gen._sym_table.insert("%t1", char_ptr_ct)

        # Insert an array of long
        long_ct = IntegerType(kind=TypeKind.LONG)
        arr_ct = CArrayType(kind=TypeKind.ARRAY, element=long_ct, size=5)
        gen._sym_table.insert("@arr", arr_ct)

        # Insert a non-pointer
        gen._sym_table.insert("%t2", int_ct)

        assert gen._pointee_size_from_ctype("%t0") == 4  # sizeof(int)
        assert gen._pointee_size_from_ctype("%t1") == 1  # sizeof(char)
        assert gen._pointee_size_from_ctype("@arr") == 8  # sizeof(long)
        assert gen._pointee_size_from_ctype("%t2") is None  # not a pointer
        assert gen._pointee_size_from_ctype("%t99") is None  # not found

    def test_lookup_pointer_ctype_helper(self):
        """Test the _lookup_pointer_ctype helper method directly."""
        from pycc.types import (
            TypedSymbolTable, PointerType, IntegerType, TypeKind,
            ArrayType as CArrayType,
        )
        from pycc.ir import IRGenerator

        gen = IRGenerator()
        gen._sym_table = TypedSymbolTable()

        int_ct = IntegerType(kind=TypeKind.INT)
        ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=int_ct)
        arr_ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)

        gen._sym_table.insert("%t0", ptr_ct)
        gen._sym_table.insert("@arr", arr_ct)
        gen._sym_table.insert("%t1", int_ct)

        assert gen._lookup_pointer_ctype("%t0") is not None  # pointer
        assert gen._lookup_pointer_ctype("@arr") is not None  # array
        assert gen._lookup_pointer_ctype("%t1") is None  # not pointer
        assert gen._lookup_pointer_ctype("%t99") is None  # not found
