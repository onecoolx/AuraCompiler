"""Test that sizeof correctly resolves typedef'd struct types.

Root cause: _type_size did not resolve typedefs, so sizeof(TypedefName)
returned the fallback 8 instead of the actual struct size. This caused
stack corruption when system structs like XVisualInfo (64 bytes) were
allocated with only 8 bytes on the stack.
"""
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code):
    import subprocess
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


class TestSizeofTypedefStruct:

    def test_typedef_struct_sizeof(self, tmp_path):
        """sizeof(TypedefName) where TypedefName is a typedef for a struct."""
        code = """
typedef struct {
    void *visual;
    long visualid;
    int screen;
    int depth;
    int xclass;
    unsigned long red_mask;
    unsigned long green_mask;
    unsigned long blue_mask;
    int colormap_size;
    int bits_per_rgb;
} XVI;

int main(void) {
    return sizeof(XVI) == 64 ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0

    def test_typedef_struct_local_var_sizeof(self, tmp_path):
        """sizeof(var) where var is a local of typedef'd struct type."""
        code = """
typedef struct { int a; int b; long c; } MyStruct;

int main(void) {
    MyStruct s;
    return sizeof(s) == 16 ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0

    def test_typedef_struct_stack_no_corruption(self, tmp_path):
        """Struct local variable gets enough stack space (no stack corruption)."""
        code = """
typedef struct {
    long data[8];
} BigStruct;

void fill(BigStruct *p) {
    int i;
    for (i = 0; i < 8; i++) p->data[i] = 42;
}

int main(void) {
    BigStruct s;
    int canary;
    canary = 99;
    fill(&s);
    return canary == 99 ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0

    def test_named_struct_typedef_sizeof(self, tmp_path):
        """sizeof with named struct typedef."""
        code = """
struct Point { int x; int y; };
typedef struct Point Point;

int main(void) {
    return sizeof(Point) == 8 ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0

    def test_chained_typedef_sizeof(self, tmp_path):
        """sizeof with chained typedefs."""
        code = """
typedef int MyInt;
typedef MyInt AnotherInt;

int main(void) {
    return sizeof(AnotherInt) == 4 ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0
