from pycc.compiler import Compiler


def test_struct_member_store_and_load(tmp_path):
    code = """
    struct Point { int x; int y; };
    int main() {
        struct Point p;
        p.x = 40;
        p.y = 2;
        return p.x + p.y;
    }
    """

    c_path = tmp_path / "m.c"
    out_path = tmp_path / "m"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    # execute
    import subprocess

    p = subprocess.run([str(out_path)], check=False)
    assert p.returncode == 42


def test_struct_char_member(tmp_path):
    code = """
    struct S { char c; int x; };
    int main() {
        struct S s;
        s.c = 2;
        s.x = 40;
        return s.c + s.x;
    }
    """
    c_path = tmp_path / "c.c"
    out_path = tmp_path / "c"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    import subprocess

    p = subprocess.run([str(out_path)], check=False)
    assert p.returncode == 42


def test_union_member_store_and_load(tmp_path):
    # In a union, all members have offset 0. Writing one member overwrites the storage.
    # We keep this test simple: write and read the same member.
    code = """
    union U { int x; char c; };
    int main() {
        union U u;
        u.x = 42;
        return u.x;
    }
    """
    c_path = tmp_path / "u.c"
    out_path = tmp_path / "u"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    import subprocess

    p = subprocess.run([str(out_path)], check=False)
    assert p.returncode == 42


def test_pointer_member_access_arrow(tmp_path):
    code = """
    struct S { int x; };
    int main() {
        struct S s;
        struct S *p;
        p = &s;
        p->x = 42;
        return p->x;
    }
    """
    c_path = tmp_path / "arrow.c"
    out_path = tmp_path / "arrow"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    import subprocess

    p = subprocess.run([str(out_path)], check=False)
    assert p.returncode == 42
