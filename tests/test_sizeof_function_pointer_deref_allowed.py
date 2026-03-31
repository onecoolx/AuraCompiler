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


def test_sizeof_deref_function_pointer_is_pointer_size_in_subset(tmp_path):
    # NOTE: In real C, `*fp` has function type and sizeof(*fp) is invalid.
    # This compiler subset currently treats function pointers as raw pointers
    # in sizeof lowering.
    code = r"""
int f(int x) { return x + 1; }

int main(void) {
  int (*fp)(int) = f;
  return (sizeof(*fp) == 8) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
