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
    return int(p.returncode)


def test_ice_allows_sizeof_type_in_enum(tmp_path):
    code = r"""
enum E {
  A = (int)sizeof(int),
  B = A + 1
};

int main(void) {
  return (B == A + 1) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
