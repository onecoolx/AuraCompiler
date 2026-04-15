"""Test that global float/double array initializers compile correctly."""
from pycc.compiler import Compiler


def test_float_array_global_init(tmp_path):
    """GLfloat mat[] = {0.5, 0.6, 0.7, 1.0}; pattern from mech.c."""
    src = tmp_path / "t.c"
    src.write_text(
        "float mat[] = {0.628281, 0.555802, 0.366065, 1.0};\n"
        "int main(void) { return 0; }\n"
    )
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(tmp_path / "t.s"))
    assert res.success, "compile failed: " + "\n".join(res.errors)


def test_double_array_global_init(tmp_path):
    src = tmp_path / "t.c"
    src.write_text(
        "double vals[] = {1.0, 2.5, 3.14};\n"
        "int main(void) { return 0; }\n"
    )
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(tmp_path / "t.s"))
    assert res.success, "compile failed: " + "\n".join(res.errors)


def test_float_array_with_multiply(tmp_path):
    """float mat[] = {128.0 * 0.4}; pattern from mech.c."""
    src = tmp_path / "t.c"
    src.write_text(
        "float mat[] = {128.0 * 0.4};\n"
        "int main(void) { return 0; }\n"
    )
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(tmp_path / "t.s"))
    assert res.success, "compile failed: " + "\n".join(res.errors)


def test_sized_float_array(tmp_path):
    src = tmp_path / "t.c"
    src.write_text(
        "float v[4] = {0.0, 0.0, 2.0, 1.0};\n"
        "int main(void) { return 0; }\n"
    )
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(tmp_path / "t.s"))
    assert res.success, "compile failed: " + "\n".join(res.errors)
