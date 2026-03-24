from __future__ import annotations

from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


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


def test_global_char_array_string_initializer(tmp_path):
    code = r'''
char s[] = "hi";
int main(void){
  return (sizeof(s)==3 && s[0]=='h' && s[1]=='i' && s[2]==0) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0


def test_global_fixed_size_char_array_string_initializer_pads_zeros(tmp_path):
        code = r'''
char s[5] = "hi";
int main(void){
    return (sizeof(s)==5 && s[0]=='h' && s[1]=='i' && s[2]==0 && s[3]==0 && s[4]==0) ? 0 : 1;
}
'''
        assert _compile_and_run(tmp_path, code) == 0


def test_global_too_small_char_array_string_initializer_truncates(tmp_path):
        code = r'''
char s[2] = "hi";
int main(void){
    return (sizeof(s)==2 && s[0]=='h' && s[1]=='i') ? 0 : 1;
}
'''
        # C89 constraint: fixed-size char array must be large enough for the
        # string literal including the terminating NUL.
        res = _compile(tmp_path, code)
        assert not res.success


def test_global_unsigned_char_array_string_initializer(tmp_path):
        code = r'''
unsigned char s[4] = "hi";
int main(void){
    return (sizeof(s)==4 && s[0]=='h' && s[1]=='i' && s[2]==0 && s[3]==0) ? 0 : 1;
}
'''
        assert _compile_and_run(tmp_path, code) == 0


def test_global_braced_string_initializer_for_char_array(tmp_path):
        code = r'''
char s[4] = {"hi"};
int main(void){
    return (sizeof(s)==4 && s[0]=='h' && s[1]=='i' && s[2]==0 && s[3]==0) ? 0 : 1;
}
'''
        assert _compile_and_run(tmp_path, code) == 0


def test_global_int_array_brace_initializer_partial_zero(tmp_path):
    code = r'''
int a[5] = {1,2};
int main(void){
  return (a[0]==1 && a[1]==2 && a[2]==0 && a[3]==0 && a[4]==0) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0


def test_global_struct_brace_initializer(tmp_path):
    code = r'''
struct P { int x; int y; };
struct P p = {1,2};
int main(void){
  return (p.x==1 && p.y==2) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0
