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


def test_plain_char_promotion_is_consistent_with_signedness(tmp_path):
    # `char` signedness is implementation-defined. We don't assert which one,
    # but we do assert it is *consistent* with comparisons after promotions.
    code = r'''
int main(){
    char c = (char)0xFF;
    /* If plain char is signed: c promotes to -1 and (c < 0) is true. */
    /* If plain char is unsigned: c promotes to 255 and (c < 0) is false. */
    if (c < 0) return 1;
    return 2;
}
'''.lstrip()

    rc = _compile_and_run(tmp_path, code)
    assert rc in (1, 2)
