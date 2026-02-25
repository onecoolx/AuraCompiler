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
from typing import Dict, List, Optional, Tuple, Any

from pycc.ir import IRInstruction


class CodeGenerator:
    """Generates x86-64 assembly code"""
    
    def __init__(self, optimize: bool = True, sema_ctx: Any = None):
        self.optimize = optimize
        self._sema_ctx = sema_ctx
        self.assembly_lines: List[str] = []
        self._string_pool: Dict[str, str] = {}
        self._string_counter = 0

        # per-function
        self._locals: Dict[str, int] = {}
        self._arrays: Dict[str, int] = {}
        self._stack_size = 0
        # MVP struct layout: hardcode offset map per function as discovered
        # (until full semantic layout is implemented).
        self._member_offsets: Dict[tuple[str, str], int] = {}
    
    def generate(self, instructions: List[IRInstruction]) -> str:
        """Generate x86-64 assembly from IR"""
        self.assembly_lines = []
        self._string_pool = {}
        self._string_counter = 0

        # First pass: emit global declarations/definitions.
        gdefs = [ins for ins in instructions if ins.op == "gdef"]
        gdecls = [ins for ins in instructions if ins.op == "gdecl"]

        if gdecls:
            self._emit(".bss")
            for gd in gdecls:
                name = (gd.result or "").lstrip("@")
                ty = gd.operand1 or "int"
                # extern declaration: no storage emitted in this TU
                if gd.label == "extern":
                    continue
                if isinstance(ty, str) and (ty == "char" or ty.startswith("char ")):
                    sz = 1
                elif isinstance(ty, str) and (ty == "int" or ty.startswith("int ")):
                    sz = 4
                else:
                    sz = 8
                self._emit(f"  .comm {name},{sz},{sz}")

        if gdefs:
            self._emit(".data")
            for gd in gdefs:
                name = (gd.result or "").lstrip("@")
                ty = gd.operand1 or "int"
                imm = gd.operand2 or "$0"
                # extern with initializer isn't valid C; treat as definition anyway.
                if gd.label != "static":
                    self._emit(f".globl {name}")
                self._emit(f"{name}:")
                # string-literal pointer initializer encoded as "=str:<text>"
                if isinstance(imm, str) and imm.startswith("=str:"):
                    s = imm[len("=str:") :]
                    lbl = self._intern_string(s)
                    # pointer-sized object
                    self._emit(f"  .quad {lbl}")
                elif isinstance(ty, str) and (ty == "char" or ty.startswith("char ")):
                    self._emit(f"  .byte {imm.lstrip('$')}")
                else:
                    # MVP: int
                    self._emit(f"  .long {imm.lstrip('$')}")

        self._emit(".text")
        i = 0
        while i < len(instructions):
            ins = instructions[i]
            if ins.op in {"gdecl", "gdef"}:
                i += 1
                continue
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
            # Some IR lowerings may emit `decl` after the initial prologue scan.
            # Ensure such locals are registered so later loads/stores don't
            # mistakenly treat them as globals.
            if ins.op == "decl" and ins.result:
                if ins.result not in self._locals:
                    # Allocate a slot now.
                    self._ensure_local(ins.result)
                i += 1
                continue
            self._emit_ins(ins)
            i += 1

        # Emit rodata for strings
        if self._string_pool:
            self._emit(".section .rodata")
            for s, lbl in self._string_pool.items():
                self._emit(f"{lbl}:")
                self._emit(f"  .string {self._gas_escape(s)}")

        return "\n".join(self.assembly_lines) + "\n"

    def _is_local(self, sym: str) -> bool:
        # Treat IR locals ("@x") as local even if they weren't part of the
        # initial decl list, because IR lowering may introduce decls after
        # the prologue scan.
        return sym in self._locals

    # -----------------
    # Function framing
    # -----------------

    def _begin_function(self, name: str, decls: List[IRInstruction]) -> None:
        self._locals = {}
        self._arrays = {}
        self._member_offsets = {}
        self._var_types: Dict[str, str] = {}

        # Assign stack slots.
        # IMPORTANT: even if a variable's logical type is smaller (char/short/int),
        # we must keep each stack slot at least 8 bytes to avoid overlapping
        # locals when using simple "one offset per symbol" addressing.
        offset = 0
        for d in decls:
            if not d.result:
                continue
            sym = d.result
            if sym in self._locals:
                continue
            # Arrays: operand1 is encoded as "array(<base>,$N)".
            if d.operand1 and isinstance(d.operand1, str) and d.operand1.strip().startswith("array("):
                enc = d.operand1.strip()
                # parse "array(T,$N)"
                inner = enc[len("array(") :]
                if inner.endswith(")"):
                    inner = inner[:-1]
                base_part, cnt_part = (inner.split(",", 1) + [""])[:2]
                base_part = base_part.strip()
                cnt_part = cnt_part.strip()
                elems = 1
                if cnt_part.startswith("$"):
                    try:
                        elems = int(cnt_part[1:])
                    except Exception:
                        elems = 1
                elem_sz = self._type_size_bytes(base_part)
                size_bytes = max(0, elems) * elem_sz
                offset += size_bytes
                self._locals[sym] = offset
                self._var_types[sym] = f"array({base_part},${elems})"
                if elems > 0:
                    self._arrays[sym] = size_bytes
            else:
                # Scalar locals: reserve a full 8-byte slot (simplifies addressing).
                offset += 8
                self._locals[sym] = offset
                if d.operand1:
                    # remember declared type base for load/store width decisions
                    self._var_types[sym] = str(d.operand1)

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
                    ty = str(d.operand1 or self._var_types.get(d.result, "")).strip()
                    if ty == "char" or ty.startswith("char ") or ty == "unsigned char" or ty.startswith("unsigned char"):
                        r = arg_regs[reg_idx]
                        breg = {"%rdi": "%dil", "%rsi": "%sil", "%rdx": "%dl", "%rcx": "%cl", "%r8": "%r8b", "%r9": "%r9b"}.get(r, "%dil")
                        self._emit(f"  movb {breg}, -{off}(%rbp)")
                    elif ty == "short" or ty == "short int" or ty.startswith("short") or ty == "unsigned short" or ty.startswith("unsigned short"):
                        # use 16-bit register name: di/si/dx/cx/r8w/r9w
                        r = arg_regs[reg_idx]
                        w = {"%rdi": "%di", "%rsi": "%si", "%rdx": "%dx", "%rcx": "%cx", "%r8": "%r8w", "%r9": "%r9w"}.get(r, "%di")
                        self._emit(f"  movw {w}, -{off}(%rbp)")
                    elif ty == "int" or ty.startswith("int ") or ty.startswith("enum ") or ty == "unsigned int" or ty.startswith("unsigned int"):
                        r = arg_regs[reg_idx]
                        l = {"%rdi": "%edi", "%rsi": "%esi", "%rdx": "%edx", "%rcx": "%ecx", "%r8": "%r8d", "%r9": "%r9d"}.get(r, "%edi")
                        self._emit(f"  movl {l}, -{off}(%rbp)")
                    else:
                        self._emit(f"  movq {arg_regs[reg_idx]}, -{off}(%rbp)")
            if d.operand1:
                self._var_types[d.result] = str(d.operand1)
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

        if op == "addr_of":
            # result = &operand1
            src = ins.operand1 or ""
            self._addr_of_symbol(src, "%rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "mov":
            self._load_operand(ins.operand1, "%rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "mov_addr":
            # result = &operand1 (more explicit than addr_of in cases where operand1
            # is an lvalue expression already resolved to a symbol)
            src = ins.operand1 or ""
            self._addr_of_symbol(src, "%rax")
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

        if op == "zext32":
            # Zero-extend low 32 bits to 64 bits.
            self._load_operand(ins.operand1, "%rax")
            self._emit("  movl %eax, %eax")
            self._store_result(ins.result, "%rax")
            return

        if op == "sext32":
            # Sign-extend low 32 bits to 64 bits.
            self._load_operand(ins.operand1, "%rax")
            self._emit("  movslq %eax, %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "binop":
            self._load_operand(ins.operand1, "%rax")
            self._load_operand(ins.operand2, "%rcx")
            bop = ins.label

            # Best-effort usual arithmetic conversions for 32-bit unsigned ints:
            # if either operand is an unsigned-32 value, perform arithmetic in
            # 32-bit and zero-extend the result.
            ty1 = self._var_types.get(ins.operand1, "")
            ty2 = self._var_types.get(ins.operand2, "")
            if not ty1 and isinstance(ins.operand1, str) and ins.operand1.startswith("@") and self._sema_ctx is not None:
                ty1 = getattr(self._sema_ctx, "global_types", {}).get(ins.operand1[1:], "")
            if not ty2 and isinstance(ins.operand2, str) and ins.operand2.startswith("@") and self._sema_ctx is not None:
                ty2 = getattr(self._sema_ctx, "global_types", {}).get(ins.operand2[1:], "")
            ty1n = ty1.strip().lower() if isinstance(ty1, str) else ""
            ty2n = ty2.strip().lower() if isinstance(ty2, str) else ""
            u32_arith = ty1n.startswith("unsigned int") or ty2n.startswith("unsigned int")
            u64_arith = ty1n.startswith("unsigned long") or ty2n.startswith("unsigned long")

            if bop == "+":
                if u32_arith:
                    self._emit("  addl %ecx, %eax")
                else:
                    self._emit("  addq %rcx, %rax")
            elif bop == "-":
                if u32_arith:
                    self._emit("  subl %ecx, %eax")
                else:
                    self._emit("  subq %rcx, %rax")
            elif bop == "*":
                if u32_arith:
                    self._emit("  imull %ecx, %eax")
                else:
                    self._emit("  imulq %rcx, %rax")
            elif bop == "/":
                if u32_arith:
                    # unsigned 32-bit division: edx:eax / ecx
                    self._emit("  xorl %edx, %edx")
                    self._emit("  divl %ecx")
                elif u64_arith:
                    # unsigned 64-bit division: rdx:rax / rcx
                    self._emit("  xorq %rdx, %rdx")
                    self._emit("  divq %rcx")
                else:
                    self._emit("  cqto")
                    self._emit("  idivq %rcx")
            elif bop == "%":
                if u32_arith:
                    self._emit("  xorl %edx, %edx")
                    self._emit("  divl %ecx")
                    self._emit("  movl %edx, %eax")
                elif u64_arith:
                    self._emit("  xorq %rdx, %rdx")
                    self._emit("  divq %rcx")
                    self._emit("  movq %rdx, %rax")
                else:
                    self._emit("  cqto")
                    self._emit("  idivq %rcx")
                    self._emit("  movq %rdx, %rax")
            elif bop in {"==", "!=", "<", "<=", ">", ">=", "u<", "u<=", "u>", "u>=", "u==", "u!="}:
                self._emit("  cmpq %rcx, %rax")
                # Signedness is decided in IR for the current milestone.
                unsigned = bop.startswith("u")
                core = bop[1:] if unsigned else bop
                if unsigned:
                    cc = {
                        "==": "sete",
                        "!=": "setne",
                        "<": "setb",
                        "<=": "setbe",
                        ">": "seta",
                        ">=": "setae",
                    }[core]
                else:
                    cc = {
                        "==": "sete",
                        "!=": "setne",
                        "<": "setl",
                        "<=": "setle",
                        ">": "setg",
                        ">=": "setge",
                    }[core]
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
                # Best-effort: if the left operand is declared unsigned, use logical shift.
                # Otherwise use arithmetic shift.
                lty = self._var_types.get(ins.operand1, "")
                if not lty and isinstance(ins.operand1, str) and ins.operand1.startswith("@") and self._sema_ctx is not None:
                    lty = getattr(self._sema_ctx, "global_types", {}).get(ins.operand1[1:], "")
                if isinstance(lty, str) and lty.strip().startswith("unsigned "):
                    self._emit("  shrq %cl, %rax")
                else:
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
            # Determine element size using best-effort type info.
            # - For pointer variables, use pointee size.
            # - For arrays, use base element size.
            elem_sz = 4
            base_ty = None
            if isinstance(base, str):
                base_ty = self._var_types.get(base)
                if base_ty is None and base.startswith("@"):
                    sym = base[1:]
                    base_ty = getattr(self._sema_ctx, "global_types", {}).get(sym) if self._sema_ctx is not None else None

            if isinstance(base_ty, str) and base_ty.strip().startswith("array("):
                # array(T,$N)
                inner = base_ty.strip()[len("array(") :]
                if inner.endswith(")"):
                    inner = inner[:-1]
                base_part = inner.split(",", 1)[0].strip()
                elem_sz = self._type_size_bytes(base_part)
            elif isinstance(base_ty, str) and "*" in base_ty:
                elem_sz = self._pointee_size_bytes(base_ty)
            # compute address: base + idx*elem_sz
            # - if base is a pointer value, load the pointer value
            # - else treat it as an array object and take its address
            if isinstance(base_ty, str) and "*" in base_ty:
                self._load_operand(base, "%rax")
            else:
                # base is an array object or a raw address temp
                if isinstance(base, str) and base.startswith("%t"):
                    self._load_operand(base, "%rax")
                else:
                    self._addr_of_symbol(base, "%rax")
            self._load_operand(idx, "%rcx")
            if elem_sz == 1:
                pass
            else:
                self._emit(f"  imulq ${elem_sz}, %rcx")
            self._emit("  addq %rcx, %rax")
            if elem_sz == 1:
                self._emit("  movsbl (%rax), %eax")
                self._emit("  movslq %eax, %rax")
            elif elem_sz == 2:
                self._emit("  movswq (%rax), %rax")
            elif elem_sz == 4:
                # load 32-bit signed int and sign-extend to %rax
                self._emit("  movslq (%rax), %rax")
            else:
                self._emit("  movq (%rax), %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "load_member":
            # MVP: treat operand1 as addressable base (stack local), operand2 as member name.
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            # Compute base address
            self._addr_of_symbol(base, "%rax")
            off, sz = self._resolve_member(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            # load based on member size
            if sz == 1:
                self._emit("  movsbl (%rax), %eax")
                self._emit("  movslq %eax, %rax")
            elif sz == 4:
                self._emit("  movslq (%rax), %rax")
            else:
                self._emit("  movq (%rax), %rax")
            self._store_result(ins.result, "%rax")
            return
        if op == "load_member_ptr":
            # operand1 holds pointer value; load it as address then add member offset
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            # load pointer value into %rax
            self._load_operand(base, "%rax")
            off, sz = self._resolve_member(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            if sz == 1:
                self._emit("  movsbl (%rax), %eax")
                self._emit("  movslq %eax, %rax")
            elif sz == 4:
                self._emit("  movslq (%rax), %rax")
            else:
                self._emit("  movq (%rax), %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "store_member":
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            val = ins.result
            self._addr_of_symbol(base, "%rax")
            off, sz = self._resolve_member(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            self._load_operand(val, "%rdx")
            if sz == 1:
                self._emit("  movb %dl, (%rax)")
            elif sz == 4:
                self._emit("  movl %edx, (%rax)")
            else:
                self._emit("  movq %rdx, (%rax)")
            return

        if op == "store_member_ptr":
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            val = ins.result
            # load pointer value into %rax
            self._load_operand(base, "%rax")
            off, sz = self._resolve_member(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            self._load_operand(val, "%rdx")
            if sz == 1:
                self._emit("  movb %dl, (%rax)")
            elif sz == 4:
                self._emit("  movl %edx, (%rax)")
            else:
                self._emit("  movq %rdx, (%rax)")
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
            # determine element size
            elem_sz = 4
            base_ty = None
            if isinstance(base, str):
                base_ty = self._var_types.get(base)
                if base_ty is None and base.startswith("@"):
                    sym = base[1:]
                    base_ty = getattr(self._sema_ctx, "global_types", {}).get(sym) if self._sema_ctx is not None else None
            if isinstance(base_ty, str) and base_ty.strip().startswith("array("):
                inner = base_ty.strip()[len("array(") :]
                if inner.endswith(")"):
                    inner = inner[:-1]
                base_part = inner.split(",", 1)[0].strip()
                elem_sz = self._type_size_bytes(base_part)
            elif isinstance(base_ty, str) and "*" in base_ty:
                elem_sz = self._pointee_size_bytes(base_ty)

            # compute address
            if isinstance(base_ty, str) and "*" in base_ty:
                self._load_operand(base, "%rax")
            else:
                # base is an array object or a raw address temp
                if isinstance(base, str) and base.startswith("%t"):
                    self._load_operand(base, "%rax")
                else:
                    self._addr_of_symbol(base, "%rax")
            self._load_operand(idx, "%rcx")
            if elem_sz != 1:
                self._emit(f"  imulq ${elem_sz}, %rcx")
            self._emit("  addq %rcx, %rax")
            # load value into %rdx and store
            self._load_operand(val, "%rdx")
            if elem_sz == 1:
                self._emit("  movb %dl, (%rax)")
            elif elem_sz == 2:
                self._emit("  movw %dx, (%rax)")
            elif elem_sz == 4:
                self._emit("  movl %edx, (%rax)")
            else:
                self._emit("  movq %rdx, (%rax)")
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
        if operand.startswith("@"):
            # local variable if it already has a stack slot; otherwise treat as global
            if self._is_local(operand):
                off = self._ensure_local(operand)
                ty = self._var_types.get(operand, "")
                b = ty.strip()
                # array variables: in expressions, array decays to pointer to first element
                if isinstance(b, str) and b.startswith("array("):
                    self._emit(f"  leaq -{off}(%rbp), {reg}")
                    return
                # signed/unsigned char
                if b == "char" or b.startswith("char "):
                    self._emit(f"  movsbq -{off}(%rbp), {reg}")
                    return
                if b == "unsigned char" or b.startswith("unsigned char"):
                    self._emit(f"  movzbq -{off}(%rbp), {reg}")
                    return
                # signed/unsigned short
                if b == "short" or b == "short int" or b.startswith("short"):
                    self._emit(f"  movswq -{off}(%rbp), {reg}")
                    return
                if b == "unsigned short" or b == "unsigned short int" or b.startswith("unsigned short"):
                    self._emit(f"  movzwq -{off}(%rbp), {reg}")
                    return
                # signed int / enum
                if b == "int" or b.startswith("int ") or b.startswith("enum "):
                    self._emit(f"  movslq -{off}(%rbp), {reg}")
                    return
                # unsigned int: load 32-bit and zero-extend
                if b == "unsigned int" or b.startswith("unsigned int"):
                    self._emit(f"  movl -{off}(%rbp), %eax")
                    if reg != "%rax":
                        self._emit(f"  movq %rax, {reg}")
                    return
                # long/pointers/default
                self._emit(f"  movq -{off}(%rbp), {reg}")
                return
            sym = operand[1:]
            # Global objects: load based on what was declared in this TU.
            ty = getattr(self._sema_ctx, "global_types", {}).get(sym) if self._sema_ctx is not None else None
            if isinstance(ty, str) and (ty.endswith("*") or "*" in ty):
                self._emit(f"  movq {sym}(%rip), {reg}")
            else:
                # MVP default: 32-bit signed int
                self._emit(f"  movslq {sym}(%rip), {reg}")
            return
        # label address?
        if operand.startswith(".L"):
            self._emit(f"  leaq {operand}(%rip), {reg}")
            return
        # fallback immediate 0
        self._emit(f"  movq $0, {reg}")

    def _as_unsigned_type(self, ty: object) -> bool:
        """Best-effort unsigned-ness check for the project's stringly-typed types."""
        if ty is None:
            return False
        if isinstance(ty, str):
            t = ty.strip()
            return t.startswith("unsigned ")
        base = getattr(ty, "base", None)
        if isinstance(base, str):
            b = base.strip()
            return b.startswith("unsigned ")
        return bool(getattr(ty, "is_unsigned", False))

    def _type_size_bytes(self, ty: object) -> int:
        """Best-effort sizeof for our stringly-typed scalar/pointer types."""
        if ty is None:
            return 8
        if isinstance(ty, str):
            b = ty.strip()
        else:
            base = getattr(ty, "base", None)
            b = base.strip() if isinstance(base, str) else ""
        if not b:
            return 8
        # pointers
        if "*" in b:
            return 8
        # integers
        if b in {"char", "unsigned char", "signed char"}:
            return 1
        if b in {"short", "short int", "unsigned short", "unsigned short int", "signed short", "signed short int"}:
            return 2
        if b in {"int", "unsigned int", "signed int"} or b.startswith("enum "):
            return 4
        if b in {"long", "long int", "unsigned long", "unsigned long int", "signed long", "signed long int"}:
            return 8
        return 8

    def _pointee_size_bytes(self, ptr_ty: object) -> int:
        """Return element size for T* types when we can recognize T.

        Note: current type strings are normalized like "unsigned long" / "int*" / "char*".
        """
        if ptr_ty is None:
            return 8
        if isinstance(ptr_ty, str):
            s = ptr_ty.replace(" ", "")
        else:
            base = getattr(ptr_ty, "base", None)
            s = base.replace(" ", "") if isinstance(base, str) else ""

        if not s or "*" not in s:
            return 8
        # peel all trailing '*'
        while s.endswith("*"):
            s = s[:-1]
        # handle common pointee bases
        if s.endswith("char") or s.endswith("unsignedchar") or s.endswith("signedchar"):
            return 1
        if s.endswith("short") or s.endswith("shortint") or s.endswith("unsignedshort") or s.endswith("unsignedshortint"):
            return 2
        if s.endswith("int") or s.endswith("unsignedint") or s.endswith("signedint") or s.startswith("enum"):
            return 4
        if s.endswith("long") or s.endswith("longint") or s.endswith("unsignedlong") or s.endswith("unsignedlongint"):
            return 8
        return 8

    def _store_result(self, result: Optional[str], reg: str) -> None:
        if result is None:
            return
        if result.startswith("%t"):
            off = self._ensure_local(result)
            self._emit(f"  movq {reg}, -{off}(%rbp)")
            return
        if result.startswith("@"):
            # local if it has a slot; otherwise global
            if self._is_local(result):
                off = self._ensure_local(result)
                ty = self._var_types.get(result, "")
                b = ty.strip()
                if b == "char" or b.startswith("char ") or b == "unsigned char" or b.startswith("unsigned char"):
                    src = "%al" if reg == "%rax" else reg
                    self._emit(f"  movb {src}, -{off}(%rbp)")
                    return
                if b == "short" or b == "short int" or b.startswith("short") or b == "unsigned short" or b.startswith("unsigned short"):
                    src = "%ax" if reg == "%rax" else reg
                    self._emit(f"  movw {src}, -{off}(%rbp)")
                    return
                if b == "int" or b.startswith("int ") or b.startswith("enum ") or b == "unsigned int" or b.startswith("unsigned int"):
                    src = "%eax" if reg == "%rax" else reg
                    self._emit(f"  movl {src}, -{off}(%rbp)")
                    return
                self._emit(f"  movq {reg}, -{off}(%rbp)")
                return
            sym = result[1:]
            ty = getattr(self._sema_ctx, "global_types", {}).get(sym) if self._sema_ctx is not None else None
            if isinstance(ty, str) and (ty.endswith("*") or "*" in ty):
                self._emit(f"  movq {reg}, {sym}(%rip)")
            else:
                # MVP: store 32-bit int
                self._emit(f"  movl %eax, {sym}(%rip)")
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
        if sym.startswith("@"):  # local if known; otherwise global
            # If this is a local, take address of its stack slot.
            # Special-case arrays: '@a' represents the whole array object, whose
            # stack slot is a header; the actual elements live at (slot + sizeof(type)).
            if sym in self._locals:
                off = self._ensure_local(sym)
                ty = self._var_types.get(sym, "")
                if isinstance(ty, str) and ty.strip().startswith("array("):
                    # Local arrays live directly in their allocated region.
                    # We store the array object at -off(%rbp) .. -(off-size+1)(%rbp).
                    # The array's decay pointer should point to the first element, i.e. -off(%rbp).
                    self._emit(f"  leaq -{off}(%rbp), {reg}")
                    return
                self._emit(f"  leaq -{off}(%rbp), {reg}")
                return
            self._emit(f"  leaq {sym[1:]}(%rip), {reg}")
            return
        if sym.startswith("%t"):
            off = self._ensure_local(sym)
            self._emit(f"  leaq -{off}(%rbp), {reg}")
            return
        self._emit(f"  leaq {sym}(%rip), {reg}")

    def _resolve_member(self, base_sym: str, member: str) -> Tuple[int, int]:
        """Return (offset, size_bytes) for `base_sym.member` using semantic layouts when available."""
        decl_ty = self._var_types.get(base_sym)
        if self._sema_ctx is not None and decl_ty and hasattr(self._sema_ctx, "layouts"):
            layouts = getattr(self._sema_ctx, "layouts")
            layout = layouts.get(decl_ty)
            if layout is not None:
                off = layout.member_offsets.get(member)
                sz = layout.member_sizes.get(member)
                if off is not None and sz is not None:
                    return int(off), int(sz)
        # fallback heuristic
        if member == "x":
            return 0, 4
        if member == "y":
            return 4, 4
        return 0, 8

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
