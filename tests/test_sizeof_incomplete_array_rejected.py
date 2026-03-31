from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_sizeof_incomplete_array_rejected(tmp_path):
    code = r"""
extern int a[];

int main(void) {
    return (int)sizeof(a);
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
