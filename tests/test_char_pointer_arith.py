from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_char_pointer_indexing_reads_bytes(tmp_path):
    code = r'''
int main(void){
  char buf[4];
  char *p;
  buf[0] = 1;
  buf[1] = 2;
  buf[2] = 3;
  buf[3] = 4;
  p = buf;
  return p[2];
}
'''
    assert _compile_and_run(tmp_path, code) == 3


def test_char_pointer_subtraction_counts_bytes(tmp_path):
    code = r'''
int main(void){
  char buf[8];
  char *p = buf;
  char *q = buf + 5;
  return (int)(q - p);
}
'''
    assert _compile_and_run(tmp_path, code) == 5
