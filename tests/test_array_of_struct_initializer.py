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


def test_array_of_struct_initializer_and_zero_fill(tmp_path):
  # Global array-of-struct brace initializer should be emitted as a constant
  # data blob with per-element zero-fill.
    code = r"""
struct S { int a; int b; };

static struct S arr[] = {
  {1},
  {2, 3},
  {0}
};

int main(void) {
  if (arr[0].a != 1) return 1;
  if (arr[0].b != 0) return 2;

  if (arr[1].a != 2) return 3;
  if (arr[1].b != 3) return 4;

  if (arr[2].a != 0) return 5;
  if (arr[2].b != 0) return 6;
  return 0;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
