from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def test_local_struct_brace_initializer_full(tmp_path):
    code = r"""
struct Point { int x; int y; };

int main(){
  struct Point p = {1, 2};
  return (p.x == 1 && p.y == 2) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_local_struct_brace_initializer_partial_zero_fill(tmp_path):
    code = r"""
struct Point { int x; int y; };

int main(){
  struct Point p = {7};
  return (p.x == 7 && p.y == 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0

    def test_local_nested_struct_zero_fill(tmp_path):
        code = r"""
        struct B { int x; int y; };
        struct A { int a; struct B b; int c; };

        int main() {
            struct A s = { 1, { 2 } };
            if (s.a != 1) return 1;
            if (s.b.x != 2) return 2;
            if (s.b.y != 0) return 3;
            if (s.c != 0) return 4;
            return 0;
        }
        """

        res = _compile_and_run(tmp_path, code)
        assert res == 0

    def test_local_nested_struct_brace_elision(tmp_path):
        code = r"""
        struct B { int x; int y; };
        struct A { int a; struct B b; int c; };

        int main() {
            struct A s = { 1, 2, 3 };
            if (s.a != 1) return 1;
            if (s.b.x != 2) return 2;
            if (s.b.y != 3) return 3;
            if (s.c != 0) return 4;
            return 0;
        }
        """

        res = _compile_and_run(tmp_path, code)
        assert res == 0
