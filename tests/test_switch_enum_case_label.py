"""Tests for switch case labels using enum constants."""
import subprocess
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code):
    c = tmp_path / "t.c"
    o = tmp_path / "t"
    c.write_text(code)
    res = Compiler(optimize=False).compile_file(str(c), str(o))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(o)], check=False, timeout=5)
    return p.returncode


def test_switch_with_enum_case_labels(tmp_path):
    """case labels using enum constants should work."""
    code = r"""
enum Color { RED, GREEN, BLUE };
int describe(enum Color c) {
    switch (c) {
        case RED: return 0;
        case GREEN: return 1;
        case BLUE: return 2;
        default: return 99;
    }
}
int main(void) {
    return (describe(RED) == 0 && describe(GREEN) == 1 && describe(BLUE) == 2) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_switch_with_enum_explicit_values(tmp_path):
    """case labels using enum constants with explicit values."""
    code = r"""
enum Mode { POINT = 0x1B00, LINE = 0x1B01, FILL = 0x1B02 };
int test(enum Mode m) {
    switch (m) {
        case POINT: return 1;
        case LINE: return 2;
        case FILL: return 3;
        default: return 0;
    }
}
int main(void) {
    return (test(POINT) == 1 && test(LINE) == 2 && test(FILL) == 3) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_switch_with_enum_and_int_mixed(tmp_path):
    """case labels mixing enum constants and integer literals."""
    code = r"""
enum Op { ADD = 1, SUB = 2 };
int calc(int op, int a, int b) {
    switch (op) {
        case ADD: return a + b;
        case SUB: return a - b;
        case 99: return 0;
        default: return -1;
    }
}
int main(void) {
    return (calc(ADD, 3, 4) == 7 && calc(SUB, 10, 3) == 7) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
