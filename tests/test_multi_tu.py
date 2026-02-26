import subprocess

from pycc.compiler import Compiler


def _compile_to_obj(tmp_path, name: str, code: str) -> str:
    c_path = tmp_path / f"{name}.c"
    o_path = tmp_path / f"{name}.o"
    c_path.write_text(code.lstrip())

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(o_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    return str(o_path)


def test_multi_tu_extern_global_across_files(tmp_path):
    # Feature C: compile two translation units and link them.
    a_o = _compile_to_obj(
        tmp_path,
        "a",
        r'''
extern int g;
int get(){ return g + 1; }
''',
    )
    b_o = _compile_to_obj(
        tmp_path,
        "b",
        r'''
int g = 41;
int get();
int main(){ return get(); }
''',
    )

    out_path = tmp_path / "a.out"
    # Use system toolchain to link.
    r = subprocess.run(["gcc", "-no-pie", a_o, b_o, "-o", str(out_path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    p = subprocess.run([str(out_path)], check=False)
    assert p.returncode == 42
