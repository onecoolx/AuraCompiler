"""Tests for struct/union by-value assignment."""
import subprocess
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(out_path)], check=False, timeout=5)
    return p.returncode


def test_struct_assign_simple(tmp_path):
    """struct S b; b = a; copies all members."""
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a;
    struct S b;
    a.x = 10;
    a.y = 20;
    b = a;
    return b.x + b.y;
}
"""
    assert _compile_and_run(tmp_path, code) == 30


def test_struct_assign_overwrite(tmp_path):
    """Assignment overwrites previous values."""
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a;
    struct S b;
    a.x = 3;
    a.y = 4;
    b.x = 99;
    b.y = 99;
    b = a;
    return b.x * 10 + b.y;
}
"""
    assert _compile_and_run(tmp_path, code) == 34


def test_struct_assign_with_char_members(tmp_path):
    """Struct with mixed-size members copies correctly."""
    code = r"""
struct S { char c; int i; };
int main(void) {
    struct S a;
    struct S b;
    a.c = 5;
    a.i = 42;
    b = a;
    return b.c + b.i;
}
"""
    assert _compile_and_run(tmp_path, code) == 47


def test_union_assign(tmp_path):
    """Union by-value assignment."""
    code = r"""
union U { int i; char c; };
int main(void) {
    union U a;
    union U b;
    a.i = 77;
    b = a;
    return b.i;
}
"""
    assert _compile_and_run(tmp_path, code) == 77


def test_struct_assign_nested(tmp_path):
    """Nested struct by-value assignment."""
    code = r"""
struct Inner { int a; int b; };
struct Outer { struct Inner in; int c; };
int main(void) {
    struct Outer x;
    struct Outer y;
    x.in.a = 1;
    x.in.b = 2;
    x.c = 3;
    y = x;
    return y.in.a + y.in.b + y.c;
}
"""
    assert _compile_and_run(tmp_path, code) == 6


def test_struct_init_from_another(tmp_path):
    """struct S b = a; initialization from another struct."""
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a;
    a.x = 11;
    a.y = 22;
    struct S b = a;
    return b.x + b.y;
}
"""
    # Note: this may require C99-style declaration-after-statement.
    # If parser doesn't support it, we test assignment form only.
    assert _compile_and_run(tmp_path, code) == 33


def test_union_assign_full_size(tmp_path):
    """Union assignment copies the full union size (largest member)."""
    code = r"""
union U { char c; int i; long l; };
int main(void) {
    union U a;
    union U b;
    a.l = 123;
    b = a;
    return (int)b.l;
}
"""
    assert _compile_and_run(tmp_path, code) == 123


def test_union_assign_preserves_all_bytes(tmp_path):
    """Union assignment copies all bytes, not just the active member."""
    code = r"""
union U { int i; char c; };
int main(void) {
    union U a;
    union U b;
    a.i = 0x01020304;
    b = a;
    /* Reading back as int should give the full value */
    return (b.i == 0x01020304) ? 1 : 0;
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_struct_init_from_var_three_members(tmp_path):
    """struct S b = a; with three int members."""
    code = r"""
struct S { int x; int y; int z; };
int main(void) {
    struct S a;
    a.x = 10;
    a.y = 20;
    a.z = 30;
    struct S b = a;
    return b.x + b.y + b.z;
}
"""
    assert _compile_and_run(tmp_path, code) == 60


def test_struct_init_from_var_nested(tmp_path):
    """struct S b = a; with nested struct members."""
    code = r"""
struct Inner { int a; int b; };
struct Outer { struct Inner in; int c; };
int main(void) {
    struct Outer x;
    x.in.a = 5;
    x.in.b = 6;
    x.c = 7;
    struct Outer y = x;
    return y.in.a + y.in.b + y.c;
}
"""
    assert _compile_and_run(tmp_path, code) == 18


def test_union_init_from_var(tmp_path):
    """union U b = a; initialization from another union variable."""
    code = r"""
union U { int i; char c; };
int main(void) {
    union U a;
    a.i = 99;
    union U b = a;
    return b.i;
}
"""
    assert _compile_and_run(tmp_path, code) == 99


def test_struct_init_value_semantics(tmp_path):
    """Modifying b after struct S b = a does not affect a."""
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a;
    a.x = 10;
    a.y = 20;
    struct S b = a;
    b.x = 99;
    b.y = 99;
    return a.x + a.y;
}
"""
    assert _compile_and_run(tmp_path, code) == 30


def test_struct_init_ir_uses_struct_copy(tmp_path):
    """Verify that struct S b = a generates struct_copy IR, not mov."""
    from pycc.compiler import Compiler as C
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a;
    a.x = 1;
    a.y = 2;
    struct S b = a;
    return b.x;
}
"""
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = C(optimize=False)
    tokens = comp.get_tokens(code)
    ast = comp.get_ast(tokens)
    sema_ctx, _ = comp.analyze_semantics(ast)
    ir, _sym_table = comp.get_ir(ast, sema_ctx=sema_ctx)
    # Find the struct_copy instruction for @b
    found_struct_copy = False
    for ins in ir:
        if ins.op == "struct_copy" and ins.result == "@b":
            found_struct_copy = True
            assert ins.meta.get("size", 0) > 0, "struct_copy should have positive size"
            break
    assert found_struct_copy, "struct S b = a should generate struct_copy IR, not mov"


def test_union_init_ir_uses_struct_copy(tmp_path):
    """Verify that union U b = a generates struct_copy IR, not mov."""
    from pycc.compiler import Compiler as C
    code = r"""
union U { int i; char c; };
int main(void) {
    union U a;
    a.i = 42;
    union U b = a;
    return b.i;
}
"""
    comp = C(optimize=False)
    tokens = comp.get_tokens(code)
    ast = comp.get_ast(tokens)
    sema_ctx, _ = comp.analyze_semantics(ast)
    ir, _sym_table = comp.get_ir(ast, sema_ctx=sema_ctx)
    found_struct_copy = False
    for ins in ir:
        if ins.op == "struct_copy" and ins.result == "@b":
            found_struct_copy = True
            assert ins.meta.get("size", 0) > 0, "struct_copy should have positive size"
            break
    assert found_struct_copy, "union U b = a should generate struct_copy IR, not mov"
