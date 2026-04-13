"""Regression test: multiple struct locals in one function.

Previously, struct locals declared after the first non-decl IR instruction
were allocated via the late-local path, placing them after the 4KB spill
area and causing stack frame corruption / segfaults.
"""
import subprocess
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code):
    c = tmp_path / "t.c"
    o = tmp_path / "t"
    c.write_text(code)
    res = Compiler(optimize=False).compile_file(str(c), str(o))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(o)], check=False, timeout=5)
    return p.returncode


def test_three_struct_locals(tmp_path):
    code = r"""
struct Node { int value; struct Node *next; };
int sum_list(struct Node *head) {
    int total = 0;
    struct Node *p = head;
    while (p) { total = total + p->value; p = p->next; }
    return total;
}
int main(void) {
    struct Node c; c.value = 3; c.next = 0;
    struct Node b; b.value = 2; b.next = &c;
    struct Node a; a.value = 1; a.next = &b;
    return sum_list(&a) == 6 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_five_struct_locals(tmp_path):
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a; a.x = 1; a.y = 2;
    struct S b; b.x = 3; b.y = 4;
    struct S c; c.x = 5; c.y = 6;
    struct S d; d.x = 7; d.y = 8;
    struct S e; e.x = 9; e.y = 10;
    return (a.x+b.x+c.x+d.x+e.x) == 25 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_locals_with_pointers(tmp_path):
    code = r"""
struct Pair { int a; int b; };
int sum(struct Pair *p) { return p->a + p->b; }
int main(void) {
    struct Pair x; x.a = 10; x.b = 20;
    struct Pair y; y.a = 30; y.b = 40;
    struct Pair z; z.a = 50; z.b = 60;
    return (sum(&x) + sum(&y) + sum(&z)) == 210 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
