"""Tests for volatile codegen (Task 4.2).

Verifies that the code generator emits '# volatile' assembly comment markers
for volatile-qualified variable accesses (mov, load, store IR ops).
"""
from __future__ import annotations

import pytest
from pycc.compiler import Compiler


def _get_asm(code: str) -> str:
    """Compile C code and return the generated assembly text."""
    comp = Compiler(optimize=False)
    tokens = comp.get_tokens(code)
    ast = comp.get_ast(tokens)
    sema_ctx, _analyzer = comp.analyze_semantics(ast)
    ir = comp.get_ir(ast, sema_ctx=sema_ctx)
    asm = comp.get_assembly(ir, sema_ctx=sema_ctx)
    return asm


# --- mov volatile markers ---

def test_volatile_local_init_has_comment():
    """volatile int x = 1; should produce assembly with '# volatile' comment."""
    code = "int main(){ volatile int x = 1; return x; }"
    asm = _get_asm(code)
    assert "# volatile" in asm, (
        "Expected '# volatile' comment in assembly for volatile local init"
    )


def test_volatile_local_assignment_has_comment():
    """volatile int x; x = 2; should produce assembly with '# volatile' comment."""
    code = "int main(){ volatile int x = 0; x = 2; return x; }"
    asm = _get_asm(code)
    # Should have multiple volatile comments: init + assignment + read
    count = asm.count("# volatile")
    assert count >= 2, (
        f"Expected >=2 '# volatile' comments for init+assignment, got {count}"
    )


def test_non_volatile_local_no_comment():
    """int x = 1; should NOT produce '# volatile' comment."""
    code = "int main(){ int x = 1; return x; }"
    asm = _get_asm(code)
    assert "# volatile" not in asm, (
        "Non-volatile variable should not produce '# volatile' comment"
    )


# --- load/store volatile markers ---

def test_volatile_pointer_deref_load_has_comment():
    """*p where p is volatile int* should produce '# volatile load' comment."""
    code = """
int main(){
    volatile int x = 10;
    volatile int *p = &x;
    int y = *p;
    return y;
}
"""
    asm = _get_asm(code)
    assert "# volatile load" in asm, (
        "Expected '# volatile load' comment for volatile pointer dereference read"
    )


def test_volatile_pointer_deref_store_has_comment():
    """*p = 42 where p is volatile int* should produce '# volatile store' comment."""
    code = """
int main(){
    volatile int x = 0;
    volatile int *p = &x;
    *p = 42;
    return x;
}
"""
    asm = _get_asm(code)
    assert "# volatile store" in asm, (
        "Expected '# volatile store' comment for volatile pointer dereference write"
    )


# --- end-to-end: volatile code still compiles and runs correctly ---

def test_volatile_codegen_compiles_and_runs(tmp_path):
    """End-to-end: volatile variable code with codegen markers compiles and runs."""
    code = r'''
int main(){
    volatile int x = 1;
    x = 2;
    volatile int *p = &x;
    *p = 42;
    return x == 42 ? 0 : 1;
}
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success


def test_volatile_loop_access_has_comments():
    """volatile accessed in a loop should produce volatile comments for each access."""
    code = """
int main(){
    volatile int x = 0;
    int i;
    for(i = 0; i < 3; i++){
        x = i;
    }
    return x;
}
"""
    asm = _get_asm(code)
    # The loop body writes to volatile x, so we should see volatile comments
    assert "# volatile" in asm, (
        "Expected '# volatile' comment for volatile access in loop"
    )
