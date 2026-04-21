"""Tests for volatile IR marking (Task 4.1).

Verifies that the IR generator sets meta['volatile'] = True on
load/store/mov instructions when accessing volatile-qualified variables.
"""
from __future__ import annotations

import pytest
from pycc.compiler import Compiler


def _get_ir(code: str):
    """Compile C code through semantics and return the IR instruction list."""
    from pycc.compiler import Compiler
    comp = Compiler(optimize=False)
    tokens = comp.get_tokens(code)
    ast = comp.get_ast(tokens)
    sema_ctx, _analyzer = comp.analyze_semantics(ast)
    ir, _sym_table = comp.get_ir(ast, sema_ctx=sema_ctx)
    return ir


def test_volatile_local_init_mov_marked():
    """volatile int x = 1; should produce a mov with volatile=True."""
    code = "int main(){ volatile int x = 1; return x; }"
    ir = _get_ir(code)
    # Find the mov that initializes x (result is @x, operand1 is $1)
    vol_movs = [i for i in ir if i.op == "mov" and i.result and "x" in i.result
                and i.meta and i.meta.get("volatile")]
    assert len(vol_movs) >= 1, "Expected at least one volatile-marked mov for init"


def test_volatile_local_assignment_mov_marked():
    """volatile int x; x = 2; should produce a mov with volatile=True."""
    code = "int main(){ volatile int x = 0; x = 2; return x; }"
    ir = _get_ir(code)
    # Find all movs to @x with volatile marking
    vol_movs = [i for i in ir if i.op == "mov" and i.result and "x" in i.result
                and i.meta and i.meta.get("volatile")]
    # Should have at least 2: one for init (x=0), one for assignment (x=2)
    assert len(vol_movs) >= 2, f"Expected >=2 volatile movs, got {len(vol_movs)}"


def test_non_volatile_local_no_marking():
    """int x = 1; should NOT produce a volatile-marked mov."""
    code = "int main(){ int x = 1; return x; }"
    ir = _get_ir(code)
    # No mov to @x should have volatile marking
    vol_movs = [i for i in ir if i.op == "mov" and i.result and "x" in i.result
                and i.meta and i.meta.get("volatile")]
    assert len(vol_movs) == 0, "Non-volatile variable should not have volatile marking"


def test_volatile_pointer_deref_store_marked():
    """*p = 42 where p is volatile int* should produce a store with volatile=True."""
    code = """
int main(){
    volatile int x = 0;
    volatile int *p = &x;
    *p = 42;
    return x;
}
"""
    ir = _get_ir(code)
    vol_stores = [i for i in ir if i.op == "store"
                  and i.meta and i.meta.get("volatile")]
    assert len(vol_stores) >= 1, "Expected volatile-marked store for *p = 42"


def test_volatile_pointer_deref_load_marked():
    """*p where p is volatile int* should produce a load with volatile=True."""
    code = """
int main(){
    volatile int x = 10;
    volatile int *p = &x;
    int y = *p;
    return y;
}
"""
    ir = _get_ir(code)
    vol_loads = [i for i in ir if i.op == "load"
                 and i.meta and i.meta.get("volatile")]
    assert len(vol_loads) >= 1, "Expected volatile-marked load for *p dereference"


def test_volatile_increment_marked():
    """volatile int x; x++; should produce volatile-marked mov for read and write."""
    code = "int main(){ volatile int x = 0; x++; return x; }"
    ir = _get_ir(code)
    # The ++ generates: mov old=@x (read), binop, mov @x=new (write)
    # Both movs involving @x should be volatile-marked
    vol_movs = [i for i in ir if i.op == "mov"
                and ((i.result and "x" in i.result) or (i.operand1 and "x" in i.operand1))
                and i.meta and i.meta.get("volatile")]
    # At least 3: init (x=0), read (old=x), write (x=new)
    assert len(vol_movs) >= 3, f"Expected >=3 volatile movs for init+increment, got {len(vol_movs)}"


def test_volatile_compound_assign_marked():
    """volatile int x; x += 5; should produce volatile-marked mov."""
    code = "int main(){ volatile int x = 1; x += 5; return x; }"
    ir = _get_ir(code)
    vol_movs = [i for i in ir if i.op == "mov"
                and i.result and "x" in i.result
                and i.meta and i.meta.get("volatile")]
    # At least 2: init (x=1) and compound assign write (x = x+5)
    assert len(vol_movs) >= 2, f"Expected >=2 volatile movs, got {len(vol_movs)}"


def test_volatile_compiles_and_runs(tmp_path):
    """End-to-end: volatile variable code compiles and runs correctly."""
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
