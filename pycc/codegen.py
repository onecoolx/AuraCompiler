"""pycc.codegen

x86-64 (System V AMD64 ABI) code generator.

This is an MVP backend to make `examples/*.c` compile and run by producing a
single assembly (.s) file that can be assembled and linked using system tools.

Supported IR ops (see `pycc.ir`):
- func_begin/func_end
- decl/param
- mov, unop, binop
- label, jmp, jz, jnz
- call, ret
- str_const
- load_index (int arrays)

Assumptions (current stage):
- integers are 64-bit in registers (we use `movq`/`cmpq` etc)
- locals are stack allocated, 8-byte aligned
- arrays are stack allocated as 8-byte elements
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pycc.ir import IRInstruction


class CodeGenerator:
    """Generates x86-64 assembly code"""
    
    def __init__(self, optimize: bool = True):
        self.optimize = optimize
        self.assembly_lines: List[str] = []
        self._string_pool: Dict[str, str] = {}
        self._string_counter = 0

        # per-function
        self._locals: Dict[str, int] = {}
        self._arrays: Dict[str, int] = {}
        self._stack_size = 0
    
    def generate(self, instructions: List[IRInstruction]) -> str:
        """Generate x86-64 assembly from IR"""
        self.assembly_lines = []
        self._string_pool = {}
        self._string_counter = 0

        self._emit(".text")
        i = 0
        while i < len(instructions):
            ins = instructions[i]
            if ins.op == "func_begin":
                fn_name = ins.label or ""
                # collect decls/params until non-decl-ish instruction
                body_start = i + 1
                decls: List[IRInstruction] = []
                while body_start < len(instructions) and instructions[body_start].op in {"decl", "param"}:
                    decls.append(instructions[body_start])
                    body_start += 1

                # Compute stack frame layout for locals/params
                self._begin_function(fn_name, decls)

                i = body_start
                continue

            if ins.op == "func_end":
                # function epilogue already emitted on ret; emit a safety label
                i += 1
                continue

            # within function body
            self._emit_ins(ins)
            i += 1

        # Emit rodata for strings
        if self._string_pool:
            self._emit(".section .rodata")
            for s, lbl in self._string_pool.items():
                self._emit(f"{lbl}:")
                self._emit(f"  .string {self._gas_escape(s)}")

        return "\n".join(self.assembly_lines) + "\n"

    # -----------------
    # Function framing
    # -----------------

    def _begin_function(self, name: str, decls: List[IRInstruction]) -> None:
        self._locals = {}
        self._arrays = {}

        # Assign stack slots. Default: 8 bytes each.
        offset = 0
        for d in decls:
            if not d.result:
                continue
            sym = d.result
            if sym in self._locals:
                continue
            # If decl carries an operand1 with element count like "$N", allocate N*8 bytes
            if d.operand1:
                try:
                    elems = int(d.operand1.lstrip("$"))
                    # C `int` is 4 bytes (C89); allocate elems * 4
                    size_bytes = elems * 4
                except Exception:
                    size_bytes = 8
                offset += size_bytes
                self._locals[sym] = offset
                # record arrays separately for clarity
                if elems > 1:
                    self._arrays[sym] = size_bytes
            else:
                offset += 8
                self._locals[sym] = offset

        # align stack to 16 bytes at call sites (after push %rbp)
        stack = offset
        if stack % 16 != 0:
            stack += 8
        self._stack_size = stack

        self._emit(f".globl {name}")
        self._emit(f"{name}:")
        self._emit("  pushq %rbp")
        self._emit("  movq %rsp, %rbp")
        if self._stack_size:
            self._emit(f"  subq ${self._stack_size}, %rsp")

        # Move params from registers into stack slots (treat @param as local)
        arg_regs = ["%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"]
        reg_idx = 0
        for d in decls:
            if d.op != "param" or not d.result:
                continue
            if reg_idx < len(arg_regs):
                off = self._locals.get(d.result)
                if off is not None:
                    self._emit(f"  movq {arg_regs[reg_idx]}, -{off}(%rbp)")
            reg_idx += 1

    # -----------------
    # Instruction emission
    # -----------------

    def _emit_ins(self, ins: IRInstruction) -> None:
        op = ins.op
        if op == "label":
            self._emit(f"{ins.label}:")
            return
        if op == "jmp":
            self._emit(f"  jmp {ins.label}")
            return
        if op in {"jz", "jnz"}:
            self._load_operand(ins.operand1, "%rax")
            self._emit("  cmpq $0, %rax")
            j = "je" if op == "jz" else "jne"
            self._emit(f"  {j} {ins.label}")
            return

        if op == "str_const":
            # result temp holds address of string
            lbl = self._intern_string(ins.operand1 or "")
            self._emit(f"  leaq {lbl}(%rip), %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "mov":
            self._load_operand(ins.operand1, "%rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "unop":
            self._load_operand(ins.operand1, "%rax")
            u = ins.label
            if u == "-":
                self._emit("  negq %rax")
            elif u == "!":
                self._emit("  cmpq $0, %rax")
                self._emit("  sete %al")
                self._emit("  movzbq %al, %rax")
            elif u == "~":
                self._emit("  notq %rax")
            elif u == "+":
                pass
            else:
                # & and * are not fully supported yet
                pass
            self._store_result(ins.result, "%rax")
            return

        if op == "binop":
            self._load_operand(ins.operand1, "%rax")
            self._load_operand(ins.operand2, "%rcx")
            bop = ins.label

            if bop == "+":
                self._emit("  addq %rcx, %rax")
            elif bop == "-":
                self._emit("  subq %rcx, %rax")
            elif bop == "*":
                self._emit("  imulq %rcx, %rax")
            elif bop == "/":
                self._emit("  cqto")
                self._emit("  idivq %rcx")
            elif bop == "%":
                self._emit("  cqto")
                self._emit("  idivq %rcx")
                self._emit("  movq %rdx, %rax")
            elif bop in {"==", "!=", "<", "<=", ">", ">="}:
                self._emit("  cmpq %rcx, %rax")
                cc = {
                    "==": "sete",
                    "!=": "setne",
                    "<": "setl",
                    "<=": "setle",
                    ">": "setg",
                    ">=": "setge",
                }[bop]
                self._emit(f"  {cc} %al")
                self._emit("  movzbq %al, %rax")
            elif bop == "&&":
                # (a!=0) && (b!=0)
                self._emit("  cmpq $0, %rax")
                self._emit("  setne %al")
                self._emit("  movzbq %al, %rax")
                self._emit("  cmpq $0, %rcx")
                self._emit("  setne %cl")
                self._emit("  movzbq %cl, %rcx")
                self._emit("  andq %rcx, %rax")
            elif bop == "||":
                self._emit("  cmpq $0, %rax")
                self._emit("  setne %al")
                self._emit("  movzbq %al, %rax")
                self._emit("  cmpq $0, %rcx")
                self._emit("  setne %cl")
                self._emit("  movzbq %cl, %rcx")
                self._emit("  orq %rcx, %rax")
                self._emit("  cmpq $0, %rax")
                self._emit("  setne %al")
                self._emit("  movzbq %al, %rax")
            elif bop == "&":
                self._emit("  andq %rcx, %rax")
            elif bop == "|":
                self._emit("  orq %rcx, %rax")
            elif bop == "^":
                self._emit("  xorq %rcx, %rax")
            elif bop == "<<":
                self._emit("  movb %cl, %cl")
                self._emit("  shlq %cl, %rax")
            elif bop == ">>":
                self._emit("  movb %cl, %cl")
                self._emit("  sarq %cl, %rax")
            else:
                # unsupported operator
                pass

            self._store_result(ins.result, "%rax")
            return

        if op == "call":
            # operand1 is function name or @name
            # args are operand strings
            arg_regs = ["%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"]
            for idx, a in enumerate(ins.args or []):
                if idx >= len(arg_regs):
                    break
                self._load_operand(a, "%rax")
                self._emit(f"  movq %rax, {arg_regs[idx]}")

            target = ins.operand1 or ""
            if target.startswith("@"):  # function symbol
                target = target[1:]
            self._emit(f"  call {target}")
            self._store_result(ins.result, "%rax")
            return

        if op == "load_index":
            # int array indexing: result = base[index]
            base = ins.operand1 or ""
            idx = ins.operand2
            # compute address: &base + idx*4 (4-byte ints)
            self._addr_of_symbol(base, "%rax")
            self._load_operand(idx, "%rcx")
            self._emit("  imulq $4, %rcx")
            self._emit("  addq %rcx, %rax")
            # load 32-bit signed int and sign-extend to %rax
            self._emit("  movslq (%rax), %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "ret":
            self._load_operand(ins.operand1, "%rax")
            self._emit("  leave")
            self._emit("  ret")
            return

        if op == "store_index":
            # store value into array: operand1=base, operand2=index, result=value
            base = ins.operand1 or ""
            idx = ins.operand2
            val = ins.result
            # compute address
            self._addr_of_symbol(base, "%rax")
            self._load_operand(idx, "%rcx")
            self._emit("  imulq $4, %rcx")
            self._emit("  addq %rcx, %rax")
            # load value into %rdx and store 32-bit
            self._load_operand(val, "%rdx")
            self._emit("  movl %edx, (%rax)")
            return

        # decl/param are handled in prologue

    # -----------------
    # Operand helpers
    # -----------------

    def _load_operand(self, operand: Optional[str], reg: str) -> None:
        if operand is None:
            self._emit(f"  movq $0, {reg}")
            return
        if operand.startswith("$"):
            self._emit(f"  movq {operand}, {reg}")
            return
        if operand.startswith("%t"):
            # temps are also stack allocated lazily
            off = self._ensure_local(operand)
            self._emit(f"  movq -{off}(%rbp), {reg}")
            return
        if operand.startswith("@"):  # variable in stack
            off = self._ensure_local(operand)
            self._emit(f"  movq -{off}(%rbp), {reg}")
            return
        # label address?
        if operand.startswith(".L"):
            self._emit(f"  leaq {operand}(%rip), {reg}")
            return
        # fallback immediate 0
        self._emit(f"  movq $0, {reg}")

    def _store_result(self, result: Optional[str], reg: str) -> None:
        if result is None:
            return
        if result.startswith("%t") or result.startswith("@"):  # stack
            off = self._ensure_local(result)
            self._emit(f"  movq {reg}, -{off}(%rbp)")
            return

    def _ensure_local(self, sym: str) -> int:
        if sym in self._locals:
            return self._locals[sym]
        # allocate new slot at end
        self._stack_size += 8
        if self._stack_size % 16 != 0:
            # keep 16B alignment roughly; grow by another slot
            self._stack_size += 8
        self._emit(f"  subq $16, %rsp")
        self._locals[sym] = self._stack_size
        return self._locals[sym]

    def _addr_of_symbol(self, sym: str, reg: str) -> None:
        if sym.startswith("@"):  # stack local
            off = self._ensure_local(sym)
            self._emit(f"  leaq -{off}(%rbp), {reg}")
            return
        if sym.startswith("%t"):
            off = self._ensure_local(sym)
            self._emit(f"  leaq -{off}(%rbp), {reg}")
            return
        self._emit(f"  leaq {sym}(%rip), {reg}")

    # -----------------
    # Strings
    # -----------------

    def _intern_string(self, s: str) -> str:
        if s in self._string_pool:
            return self._string_pool[s]
        lbl = f".LC{self._string_counter}"
        self._string_counter += 1
        self._string_pool[s] = lbl
        return lbl

    def _gas_escape(self, s: str) -> str:
        # Produce a GAS-compatible quoted string literal
        escaped = (
            s.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            .replace("\r", "\\r")
            .replace('"', '\\"')
        )
        return f'"{escaped}"'

    def _emit(self, line: str) -> None:
        self.assembly_lines.append(line)
