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


def test_local_char_array_string_initializer(tmp_path):
    code = r"""
int main(){
  char s[] = "hi";
    return (s[0] == 'h' && s[1] == 'i' && s[2] == 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_local_char_array_fixed_size_string_initializer_zero_fill(tmp_path):
        code = r"""
int main(){
    char s[5] = "hi";
    return (s[0] == 'h' && s[1] == 'i' && s[2] == 0 && s[3] == 0 && s[4] == 0) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_brace_initializer(tmp_path):
    code = r"""
int main(){
  int a[3] = {1, 2, 3};
  return (a[0] + a[1] + a[2]) == 6 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_local_char_array_fixed_size_string_initializer_truncate(tmp_path):
        code = r"""
int main(){
    char s[2] = "hi";
    return (s[0] == 'h' && s[1] == 'i') ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_zero_fill_brace_initializer(tmp_path):
    code = r"""
int main(){
  int a[3] = {1};
  return (a[0] == 1 && a[1] == 0 && a[2] == 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_brace_initializer_truncate(tmp_path):
                code = r"""
int main(){
        int a[2] = {1, 2, 3, 4};
        return (a[0] == 1 && a[1] == 2) ? 0 : 1;
}
""".lstrip()
                assert _compile_and_run(tmp_path, code) == 0


def test_local_char_array_infer_size_from_string_initializer(tmp_path):
        code = r"""
int main(){
    char s[] = "hi";
    return (sizeof(s) == 3 && s[0] == 'h' && s[1] == 'i' && s[2] == 0) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_infer_size_from_brace_initializer(tmp_path):
        code = r"""
int main(){
    int a[] = {1, 2, 3, 4};
    return (sizeof(a) == 16 && (a[0] + a[1] + a[2] + a[3]) == 10) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_local_char_array_infer_size_from_brace_initializer(tmp_path):
        code = r"""
int main(){
    char s[] = {'h', 'i', 0};
    return (sizeof(s) == 3 && s[0] == 'h' && s[1] == 'i' && s[2] == 0) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_local_char_array_brace_initializer_zero_fill(tmp_path):
        code = r"""
int main(){
    char s[5] = {'h', 'i'};
    return (s[0] == 'h' && s[1] == 'i' && s[2] == 0 && s[3] == 0 && s[4] == 0) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_infer_size_singleton_initializer(tmp_path):
        code = r"""
int main(){
    int a[] = {1};
    return (sizeof(a) == 4 && a[0] == 1) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_infer_size_multi_element_initializer(tmp_path):
        code = r"""
int main(){
    int a[] = {1, 2, 3};
    return (sizeof(a) == 12 && a[2] == 3) ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_local_char_array_infer_size_singleton_initializer(tmp_path):
        code = r"""
int main(){
    char s[] = {'h'};
    return (sizeof(s) == 1 && s[0] == 'h') ? 0 : 1;
}
""".lstrip()
        assert _compile_and_run(tmp_path, code) == 0
