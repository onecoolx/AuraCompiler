from __future__ import annotations

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


def test_global_char_array_indexing_reads_correct_bytes(tmp_path):
    code = r'''
char s[] = "hi";
int main(void){
  return (s[0] == 'h' && s[1] == 'i' && s[2] == 0) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0
