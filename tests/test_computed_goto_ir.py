"""Tests for computed goto IR generation (tasks 5.1, 5.2, 6.3).

Verifies:
- LabelAddress generates label_addr instruction with correct label name
- LabelAddress temp is typed as void *
- Label naming follows .Luser_<func>_<name> convention
- LabelAddress in static dispatch table initializers emits gdef_ptr_array with symbol entries
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction
from pycc.ast_nodes import (
    Program, FunctionDecl, CompoundStmt, ReturnStmt, IntLiteral,
    Declaration, LabelAddress, LabelStmt, ExpressionStmt, Initializer,
)


def _make_type(base, is_pointer=False):
    """Create a minimal AST Type-like object."""
    t = MagicMock()
    t.base = base
    t.is_pointer = is_pointer
    t.is_volatile = False
    t.pointer_level = 1 if is_pointer else 0
    return t


def _make_sema_ctx():
    """Create a minimal SemanticContext-like object."""
    ctx = MagicMock()
    ctx.typedefs = {}
    ctx.layouts = {}
    ctx.global_types = {}
    ctx.function_sigs = {}
    ctx.global_decl_types = {}
    return ctx


def _make_function_with_label_address(func_name, label_name):
    """Create a function that uses &&label_name in an expression statement."""
    rt = _make_type("int")
    label_addr_expr = LabelAddress(line=1, column=1, label_name=label_name)
    # Wrap in expression statement (value discarded, but IR still generated)
    expr_stmt = ExpressionStmt(line=1, column=1, expression=label_addr_expr)
    # The label itself (required for valid code, but IR gen doesn't validate)
    label_stmt = LabelStmt(
        line=2, column=1, name=label_name,
        statement=ReturnStmt(line=2, column=1, value=IntLiteral(line=2, column=1, value=0))
    )
    body = CompoundStmt(line=0, column=0, statements=[expr_stmt, label_stmt])
    fn = FunctionDecl(
        line=0, column=0,
        name=func_name,
        return_type=rt,
        parameters=[],
        body=body,
    )
    return fn


def test_label_address_emits_label_addr_instruction():
    """LabelAddress node generates a label_addr IR instruction."""
    fn = _make_function_with_label_address("my_func", "target")
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    instructions = gen.generate(prog)

    # Find the label_addr instruction
    label_addr_instrs = [i for i in instructions if i.op == "label_addr"]
    assert len(label_addr_instrs) == 1

    ins = label_addr_instrs[0]
    assert ins.label == ".Luser_my_func_target"
    assert ins.result is not None
    assert ins.result.startswith("%t")


def test_label_address_result_typed_void_ptr():
    """LabelAddress temp should be typed as void *."""
    fn = _make_function_with_label_address("dispatch", "op_add")
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    gen.generate(prog)

    # Find the label_addr instruction
    label_addr_instrs = [i for i in gen.instructions if i.op == "label_addr"]
    assert len(label_addr_instrs) == 1

    result_temp = label_addr_instrs[0].result
    # Check _var_types records it as void *
    assert gen._var_types.get(result_temp) == "void *"


def test_label_address_naming_convention():
    """Label naming follows .Luser_<funcname>_<labelname> format."""
    fn = _make_function_with_label_address("vm_loop", "case_LOAD")
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    gen.generate(prog)

    label_addr_instrs = [i for i in gen.instructions if i.op == "label_addr"]
    assert len(label_addr_instrs) == 1
    assert label_addr_instrs[0].label == ".Luser_vm_loop_case_LOAD"


def test_label_address_multiple_in_same_function():
    """Multiple &&label expressions in the same function each get their own temp."""
    rt = _make_type("int")
    expr1 = ExpressionStmt(line=1, column=1,
                           expression=LabelAddress(line=1, column=1, label_name="L1"))
    expr2 = ExpressionStmt(line=2, column=1,
                           expression=LabelAddress(line=2, column=1, label_name="L2"))
    label1 = LabelStmt(line=3, column=1, name="L1",
                       statement=ReturnStmt(line=3, column=1, value=IntLiteral(line=3, column=1, value=1)))
    label2 = LabelStmt(line=4, column=1, name="L2",
                       statement=ReturnStmt(line=4, column=1, value=IntLiteral(line=4, column=1, value=2)))
    body = CompoundStmt(line=0, column=0, statements=[expr1, expr2, label1, label2])
    fn = FunctionDecl(line=0, column=0, name="multi", return_type=rt,
                      parameters=[], body=body)
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    gen.generate(prog)

    label_addr_instrs = [i for i in gen.instructions if i.op == "label_addr"]
    assert len(label_addr_instrs) == 2
    assert label_addr_instrs[0].label == ".Luser_multi_L1"
    assert label_addr_instrs[1].label == ".Luser_multi_L2"
    # Each gets a distinct temp
    assert label_addr_instrs[0].result != label_addr_instrs[1].result
    # Both typed as void *
    assert gen._var_types[label_addr_instrs[0].result] == "void *"
    assert gen._var_types[label_addr_instrs[1].result] == "void *"


# --- Tests for ComputedGoto (indirect_jump) ---

from pycc.ast_nodes import ComputedGoto, Identifier, ArrayAccess


def _make_function_with_computed_goto(func_name, target_expr, extra_stmts=None):
    """Create a function containing goto *target_expr."""
    rt = _make_type("int")
    goto_stmt = ComputedGoto(line=1, column=1, target=target_expr)
    stmts = list(extra_stmts or [])
    stmts.append(goto_stmt)
    stmts.append(ReturnStmt(line=9, column=1, value=IntLiteral(line=9, column=1, value=0)))
    body = CompoundStmt(line=0, column=0, statements=stmts)
    fn = FunctionDecl(
        line=0, column=0,
        name=func_name,
        return_type=rt,
        parameters=[],
        body=body,
    )
    return fn


def test_computed_goto_emits_indirect_jump():
    """ComputedGoto generates an indirect_jump IR instruction."""
    # goto *ptr where ptr is a local variable
    # We need a declaration for ptr so _gen_expr can resolve it
    ptr_type = _make_type("void", is_pointer=True)
    ptr_decl = Declaration(
        line=1, column=1, name="ptr", type=ptr_type,
        initializer=None,
    )
    target = Identifier(line=2, column=1, name="ptr")
    fn = _make_function_with_computed_goto("test_fn", target, extra_stmts=[ptr_decl])
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    instructions = gen.generate(prog)

    # Find the indirect_jump instruction
    ij_instrs = [i for i in instructions if i.op == "indirect_jump"]
    assert len(ij_instrs) == 1
    ins = ij_instrs[0]
    # operand1 should be a temp holding the loaded address
    assert ins.operand1 is not None


def test_computed_goto_operand_is_temp():
    """indirect_jump operand should be a temp from evaluating the target expression."""
    ptr_type = _make_type("void", is_pointer=True)
    ptr_decl = Declaration(
        line=1, column=1, name="addr", type=ptr_type,
        initializer=None,
    )
    target = Identifier(line=2, column=1, name="addr")
    fn = _make_function_with_computed_goto("jump_fn", target, extra_stmts=[ptr_decl])
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    gen.generate(prog)

    ij_instrs = [i for i in gen.instructions if i.op == "indirect_jump"]
    assert len(ij_instrs) == 1
    # The operand should be a temp (starts with %t or @)
    op = ij_instrs[0].operand1
    assert op.startswith("%t") or op.startswith("@")


def test_computed_goto_with_label_address():
    """goto *&&label pattern: label_addr followed by indirect_jump."""
    rt = _make_type("int")
    # Build: goto *&&target; target: return 42;
    label_addr_expr = LabelAddress(line=1, column=1, label_name="target")
    goto_stmt = ComputedGoto(line=1, column=1, target=label_addr_expr)
    label_stmt = LabelStmt(
        line=2, column=1, name="target",
        statement=ReturnStmt(line=2, column=1, value=IntLiteral(line=2, column=1, value=42))
    )
    body = CompoundStmt(line=0, column=0, statements=[goto_stmt, label_stmt])
    fn = FunctionDecl(line=0, column=0, name="combo", return_type=rt,
                      parameters=[], body=body)
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    gen.generate(prog)

    # Should have both label_addr and indirect_jump
    la_instrs = [i for i in gen.instructions if i.op == "label_addr"]
    ij_instrs = [i for i in gen.instructions if i.op == "indirect_jump"]
    assert len(la_instrs) == 1
    assert len(ij_instrs) == 1

    # indirect_jump operand should be the result of label_addr
    assert ij_instrs[0].operand1 == la_instrs[0].result


# --- Tests for static dispatch table (task 6.3) ---


def test_static_dispatch_table_label_addresses():
    """static void *table[] = {&&L1, &&L2, &&L3} emits gdef_ptr_array with label symbols.

    Validates: Requirements 4.4
    """
    rt = _make_type("int")
    # Build: static void *table[] = {&&L1, &&L2, &&L3};
    ptr_type = _make_type("void", is_pointer=True)
    init = Initializer(line=1, column=1, elements=[
        (None, LabelAddress(line=1, column=1, label_name="L1")),
        (None, LabelAddress(line=1, column=1, label_name="L2")),
        (None, LabelAddress(line=1, column=1, label_name="L3")),
    ])
    table_decl = Declaration(
        line=1, column=1, name="table", type=ptr_type,
        initializer=init, storage_class="static",
    )
    # Add labels so the function is valid
    label1 = LabelStmt(line=3, column=1, name="L1",
                       statement=ReturnStmt(line=3, column=1, value=IntLiteral(line=3, column=1, value=1)))
    label2 = LabelStmt(line=4, column=1, name="L2",
                       statement=ReturnStmt(line=4, column=1, value=IntLiteral(line=4, column=1, value=2)))
    label3 = LabelStmt(line=5, column=1, name="L3",
                       statement=ReturnStmt(line=5, column=1, value=IntLiteral(line=5, column=1, value=3)))
    body = CompoundStmt(line=0, column=0, statements=[table_decl, label1, label2, label3])
    fn = FunctionDecl(line=0, column=0, name="dispatch", return_type=rt,
                      parameters=[], body=body)
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    instructions = gen.generate(prog)

    # Should emit a gdef_ptr_array instruction for the static table
    gpa_instrs = [i for i in instructions if i.op == "gdef_ptr_array"]
    assert len(gpa_instrs) == 1

    gpa = gpa_instrs[0]
    # The global name should contain the local static mangled name
    assert "table" in gpa.result
    assert gpa.label == "static"

    # Entries should be symbol references with correct label names
    entries = gpa.meta["entries"]
    assert len(entries) == 3
    assert entries[0] == ("symbol", ".Luser_dispatch_L1")
    assert entries[1] == ("symbol", ".Luser_dispatch_L2")
    assert entries[2] == ("symbol", ".Luser_dispatch_L3")


def test_static_dispatch_table_mixed_with_null():
    """static void *table[] = {&&L1, (void*)0, &&L2} handles mixed entries.

    Validates: Requirements 4.4
    """
    rt = _make_type("int")
    ptr_type = _make_type("void", is_pointer=True)

    # (void*)0 is a null pointer constant
    null_expr = IntLiteral(line=1, column=1, value=0)

    init = Initializer(line=1, column=1, elements=[
        (None, LabelAddress(line=1, column=1, label_name="op_add")),
        (None, null_expr),
        (None, LabelAddress(line=1, column=1, label_name="op_sub")),
    ])
    table_decl = Declaration(
        line=1, column=1, name="ops", type=ptr_type,
        initializer=init, storage_class="static",
    )
    label1 = LabelStmt(line=3, column=1, name="op_add",
                       statement=ReturnStmt(line=3, column=1, value=IntLiteral(line=3, column=1, value=10)))
    label2 = LabelStmt(line=4, column=1, name="op_sub",
                       statement=ReturnStmt(line=4, column=1, value=IntLiteral(line=4, column=1, value=20)))
    body = CompoundStmt(line=0, column=0, statements=[table_decl, label1, label2])
    fn = FunctionDecl(line=0, column=0, name="vm_exec", return_type=rt,
                      parameters=[], body=body)
    prog = Program(line=0, column=0, declarations=[fn])

    gen = IRGenerator()
    gen._sema_ctx = _make_sema_ctx()
    instructions = gen.generate(prog)

    gpa_instrs = [i for i in instructions if i.op == "gdef_ptr_array"]
    assert len(gpa_instrs) == 1

    entries = gpa_instrs[0].meta["entries"]
    assert len(entries) == 3
    assert entries[0] == ("symbol", ".Luser_vm_exec_op_add")
    assert entries[1] == ("null", 0)
    assert entries[2] == ("symbol", ".Luser_vm_exec_op_sub")
