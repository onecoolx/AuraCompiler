"""Tests for switch/case with enum constant labels."""
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
    """switch/case using enum constants as case labels."""
    code = r"""
enum Color { RED, GREEN, BLUE };
int describe(enum Color c) {
    switch (c) {
        case RED: return 1;
        case GREEN: return 2;
        case BLUE: return 3;
        default: return 0;
    }
}
int main(void) {
    return (describe(RED) == 1 && describe(GREEN) == 2 && describe(BLUE) == 3) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_switch_with_enum_hex_values(tmp_path):
    """switch/case using enum constants with hex values."""
    code = r"""
enum Mode { MODE_A = 0x0000, MODE_B = 0x0001, MODE_C = 0x0002 };
int check(enum Mode m) {
    switch (m) {
        case MODE_A: return 10;
        case MODE_B: return 20;
        case MODE_C: return 30;
    }
    return 0;
}
int main(void) {
    return (check(MODE_A) == 10 && check(MODE_B) == 20 && check(MODE_C) == 30) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_switch_with_enum_and_default(tmp_path):
    """switch/case with enum labels and default fallback."""
    code = r"""
enum Op { OP_ADD, OP_SUB, OP_MUL };
int compute(enum Op op, int a, int b) {
    switch (op) {
        case OP_ADD: return a + b;
        case OP_SUB: return a - b;
        case OP_MUL: return a * b;
        default: return -1;
    }
}
int main(void) {
    return compute(OP_ADD, 3, 4) == 7 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
