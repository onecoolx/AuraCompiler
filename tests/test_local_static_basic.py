import subprocess

from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_local_static_persists_across_calls(tmp_path):
    code = r'''
int f(){
    static int x = 0;
    x = x + 1;
    return x;
}

int main(){
    int a = f();
    int b = f();
    /* local static should keep state across calls */
    return a * 10 + b;
}
'''.lstrip()

    assert _compile_and_run(tmp_path, code) == 12
