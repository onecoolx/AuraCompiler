"""End-to-end tests for GCC computed goto (labels as values) extension."""

import subprocess

from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    """Compile C code with pycc and run the resulting binary, returning exit code."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_simple_computed_goto(tmp_path):
    """Simple computed goto: take label address, jump via pointer."""
    code = """\
int main() {
    void *target = &&done;
    goto *target;
    return 1;
done:
    return 42;
}
"""
    assert _compile_and_run(tmp_path, code) == 42


def test_dispatch_table(tmp_path):
    """Dispatch table pattern: label address array + indexed jump (opcode dispatch)."""
    code = """\
int main() {
    void *table[3];
    table[0] = &&op_add;
    table[1] = &&op_sub;
    table[2] = &&op_done;

    int result = 10;
    int op = 0;

    goto *table[op];

op_add:
    result = result + 5;
    op = 1;
    goto *table[op];

op_sub:
    result = result - 3;
    op = 2;
    goto *table[op];

op_done:
    return result;
}
"""
    # 10 + 5 - 3 = 12
    assert _compile_and_run(tmp_path, code) == 12


def test_vm_dispatch_loop(tmp_path):
    """VM main loop pattern: dispatch table with multiple opcodes and a program counter.

    Simulates a simple bytecode VM: ADD 5, ADD 3, SUB 1, HALT.
    Expected: 0 + 5 + 3 - 1 = 7.
    """
    code = """\
int main() {
    int opcodes[4];
    opcodes[0] = 0;
    opcodes[1] = 0;
    opcodes[2] = 1;
    opcodes[3] = 2;

    int operands[4];
    operands[0] = 5;
    operands[1] = 3;
    operands[2] = 1;
    operands[3] = 0;

    void *dispatch[3];
    dispatch[0] = &&op_add;
    dispatch[1] = &&op_sub;
    dispatch[2] = &&op_halt;

    int acc = 0;
    int pc = 0;

    goto *dispatch[opcodes[pc]];

op_add:
    acc = acc + operands[pc];
    pc = pc + 1;
    goto *dispatch[opcodes[pc]];

op_sub:
    acc = acc - operands[pc];
    pc = pc + 1;
    goto *dispatch[opcodes[pc]];

op_halt:
    return acc;
}
"""
    # 0 + 5 + 3 - 1 = 7
    assert _compile_and_run(tmp_path, code) == 7
