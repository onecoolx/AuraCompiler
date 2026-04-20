"""pycc.codegen — x86-64 SysV code generator.

Produces assembly (.s) from IR, supporting integer and SSE/SSE2 float ops.

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

import struct as _struct
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

from pycc.ir import IRInstruction


# ---------------------------------------------------------------------------
# SysV AMD64 ABI struct classification (eightbyte algorithm)
# ---------------------------------------------------------------------------

class EightbyteClass:
    """SysV ABI eightbyte classification constants."""
    NO_CLASS = 0
    INTEGER = 1
    SSE = 2
    MEMORY = 3


def _classify_field(type_str: str) -> int:
    """Classify a single scalar field type into an EightbyteClass value.

    Integer types (char, short, int, long, pointer, enum) → INTEGER
    Float types (float, double) → SSE
    long double → MEMORY (causes entire struct to degrade)
    """
    t = type_str.strip()

    # Pointer types (contain '*')
    if "*" in t:
        return EightbyteClass.INTEGER

    # long double → MEMORY (80-bit x87, 16-byte aligned on x86-64)
    if t == "long double":
        return EightbyteClass.MEMORY

    # SSE types
    if t in ("float", "double"):
        return EightbyteClass.SSE

    # Integer / enum types → INTEGER
    # This covers: char, signed char, unsigned char, short, int, long,
    # long long, unsigned variants, and enum types.
    return EightbyteClass.INTEGER


def _merge_classes(a: int, b: int) -> int:
    """Merge two eightbyte classifications.  Priority: MEMORY > INTEGER > SSE > NO_CLASS."""
    if a == EightbyteClass.MEMORY or b == EightbyteClass.MEMORY:
        return EightbyteClass.MEMORY
    if a == EightbyteClass.INTEGER or b == EightbyteClass.INTEGER:
        return EightbyteClass.INTEGER
    if a == EightbyteClass.SSE or b == EightbyteClass.SSE:
        return EightbyteClass.SSE
    return EightbyteClass.NO_CLASS


def classify_struct(struct_type: str, layout: "StructLayout") -> list:
    """Classify a struct/union type according to the SysV AMD64 ABI.

    Returns a list of EightbyteClass values (at most 2 elements).
    If the struct is > 16 bytes or contains a ``long double`` member the
    entire struct is classified as MEMORY (``[EightbyteClass.MEMORY]``).

    *layout* is a ``pycc.semantics.StructLayout`` instance that provides
    ``size``, ``member_offsets``, ``member_sizes``, and ``member_types``.
    """
    size = int(getattr(layout, "size", 0) or 0)

    # Rule 1: structs larger than 16 bytes → MEMORY
    if size > 16:
        return [EightbyteClass.MEMORY]

    # Empty struct edge-case (size 0) – treat as NO_CLASS
    if size == 0:
        return [EightbyteClass.NO_CLASS]

    member_offsets = getattr(layout, "member_offsets", {}) or {}
    member_sizes = getattr(layout, "member_sizes", {}) or {}
    member_types = getattr(layout, "member_types", {}) or {}

    # Determine number of eightbytes (1 or 2)
    num_eightbytes = 1 if size <= 8 else 2
    classes = [EightbyteClass.NO_CLASS] * num_eightbytes

    for name, offset in member_offsets.items():
        mtype = member_types.get(name, "int")
        field_class = _classify_field(mtype)

        # If any field is MEMORY (e.g. long double), entire struct → MEMORY
        if field_class == EightbyteClass.MEMORY:
            return [EightbyteClass.MEMORY]

        # Determine which eightbyte this field falls into (0 or 1)
        eb_index = 0 if offset < 8 else 1
        # Clamp to valid range (should not happen for size ≤ 16, but be safe)
        if eb_index >= num_eightbytes:
            eb_index = num_eightbytes - 1

        classes[eb_index] = _merge_classes(classes[eb_index], field_class)

    # Replace any remaining NO_CLASS with INTEGER (conservative default for
    # padding-only eightbytes – the ABI treats them as INTEGER).
    for i in range(len(classes)):
        if classes[i] == EightbyteClass.NO_CLASS:
            classes[i] = EightbyteClass.INTEGER

    return classes


def get_struct_pass_mode(classification: list) -> str:
    """Determine the parameter/return passing mode from a classification list.

    Returns one of:
      - ``'registers'``   – fits in GP/SSE registers
      - ``'stack'``       – passed on the stack (fallback when regs exhausted;
                            caller is responsible for checking register availability)
      - ``'hidden_ptr'``  – MEMORY class; caller allocates space and passes a
                            hidden pointer (used for large structs / long double)
    """
    if not classification:
        return "stack"

    if any(c == EightbyteClass.MEMORY for c in classification):
        return "hidden_ptr"

    # All eightbytes are INTEGER or SSE → eligible for register passing.
    return "registers"


class CodeGenerator:
    """Generates x86-64 assembly code"""
    
    def __init__(self, optimize: bool = True, sema_ctx: Any = None, pic: bool = False):
        self.optimize = optimize
        self._sema_ctx = sema_ctx
        self._pic = pic
        self.assembly_lines: List[str] = []
        self._string_pool: Dict[str, str] = {}
        self._string_counter = 0
        self._float_pool: Dict[str, str] = {}  # key: "type:bits" -> label
        self._float_counter = 0

        # SysV AMD64 varargs ABI constants (glibc).
        self._VARARGS_GP_SAVE_AREA_SIZE = 48
        self._VARARGS_REG_SAVE_AREA_SIZE = 176
        self._VARARGS_VA_LIST_TAG_AREA_SIZE = 32
        self._VARARGS_FIRST_STACK_ARG_OFF = 16

        # per-function
        self._locals: Dict[str, int] = {}
        self._arrays: Dict[str, int] = {}
        self._stack_size = 0
        self._fn_name: Optional[str] = None
        self._fn_ret_ty: str = ""
        # Fixed spill area for temporaries (to avoid dynamic %rsp adjustment).
        self._spill_capacity = 0
        self._spill_used = 0
        # Total size of declared locals area for current function (bytes).
        self._locals_base = 0
        # struct layout: per-function member offset map
        # (until full semantic layout is implemented).
        self._member_offsets: Dict[tuple[str, str], int] = {}
    
    def generate(self, instructions: List[IRInstruction]) -> str:
        """Generate x86-64 assembly from IR"""
        self.assembly_lines = []
        self._string_pool = {}
        self._string_counter = 0
        # Best-effort type table across the whole function. This is needed for
        # temps like `%t0` produced by `addr_index` so later ops (load_member)
        # know it is a pointer value.
        self._var_types: Dict[str, str] = {}
        # Optional per-temp pointer arithmetic step overrides (bytes).
        # Populated from IRInstruction.meta (e.g. for pointer-to-array decay).
        self._ptr_step_bytes: Dict[str, int] = {}
        # function symbols in this translation unit (for function pointer decay)
        self._functions = {ins.label for ins in instructions if ins.op == "func_begin" and ins.label}

        # First pass: emit global declarations/definitions.
        gdefs = [ins for ins in instructions if ins.op == "gdef"]
        gblobs = [ins for ins in instructions if ins.op == "gdef_blob"]
        gfloats = [ins for ins in instructions if ins.op == "gdef_float"]
        gptrarrs = [ins for ins in instructions if ins.op == "gdef_ptr_array"]
        gstructs = [ins for ins in instructions if ins.op == "gdef_struct"]
        gdecls = [ins for ins in instructions if ins.op == "gdecl"]

        # Symbols with definitions should not also get .bss tentative entries
        defined_syms = {(ins.result or "").lstrip("@") for ins in instructions if ins.op in ("gdef", "gdef_blob", "gdef_float", "gdef_ptr_array", "gdef_struct")}

        if gdecls:
            self._emit(".bss")
            for gd in gdecls:
                name = (gd.result or "").lstrip("@")
                if name in defined_syms:
                    continue
                ty = gd.operand1 or "int"
                # extern declaration: no storage emitted in this TU
                if gd.label == "extern":
                    continue
                # Only emit tentative definitions and local statics as common/bss symbols.
                if gd.label not in {None, "", "tentative", "static"}:
                    continue
                meta = gd.meta or {}
                if "size" in meta:
                    sz = int(meta["size"])
                elif isinstance(ty, str) and ty.startswith("array("):
                    # Parse array(T,$N) to compute size
                    inner = ty[len("array("):]
                    if inner.endswith(")"):
                        inner = inner[:-1]
                    parts = inner.split(",", 1)
                    base_part = parts[0].strip()
                    cnt_part = parts[1].strip() if len(parts) > 1 else "$1"
                    n = int(cnt_part.lstrip("$")) if cnt_part.startswith("$") else 1
                    elem_sz = self._type_size_bytes(base_part)
                    sz = n * elem_sz
                elif isinstance(ty, str) and (ty.startswith("struct ") or ty.startswith("union ")) and self._sema_ctx is not None:
                    layout = getattr(self._sema_ctx, "layouts", {}).get(ty)
                    sz = int(getattr(layout, "size", 8)) if layout is not None else 8
                elif isinstance(ty, str) and (ty == "char" or ty.startswith("char ")):
                    sz = 1
                elif isinstance(ty, str) and (ty == "int" or ty.startswith("int ")):
                    sz = 4
                else:
                    sz = 8
                self._emit(f"  .comm {name},{sz},{sz}")

        if gdefs or gblobs or gfloats or gptrarrs or gstructs:
            self._emit(".data")
            for gd in gblobs:
                name = (gd.result or "").lstrip("@")
                ty = gd.operand1 or "int"
                blob = gd.operand2 or "blob:"
                if gd.label != "static":
                    self._emit(f".globl {name}")
                self._emit(f"{name}:")
                if isinstance(blob, str) and blob.startswith("blob:"):
                    hexbytes = blob[len("blob:") :]
                    # emit as raw bytes
                    for i in range(0, len(hexbytes), 2):
                        b = int(hexbytes[i : i + 2] or "00", 16)
                        self._emit(f"  .byte {b}")
                    # Ensure any following objects are correctly aligned.
                    # In particular, struct blobs may include padding and may
                    # require natural alignment for correct field loads.
                    try:
                        if isinstance(ty, str) and (ty.startswith("struct ") or ty.startswith("union ")) and self._sema_ctx is not None:
                            layout = getattr(self._sema_ctx, "layouts", {}).get(ty)
                            align = int(getattr(layout, "align", 1)) if layout is not None else 1
                        elif isinstance(ty, str) and (ty == "int" or ty.startswith("int ")):
                            align = 4
                        else:
                            align = 1
                        if align and align > 1:
                            self._emit(f"  .p2align {max(0, (align).bit_length()-1)}")
                    except Exception:
                        pass
                else:
                    # fallback: zero
                    self._emit("  .byte 0")

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
                    # int
                    self._emit(f"  .long {imm.lstrip('$')}")

            for gf in gfloats:
                name = (gf.result or "").lstrip("@")
                fp_type = (gf.meta or {}).get("fp_type", "double")
                val = float(gf.operand1 or "0.0")
                if gf.label != "static":
                    self._emit(f".globl {name}")
                if fp_type == "long double":
                    self._emit(f"  .align 16")
                    self._emit(f"{name}:")
                    # Emit 80-bit extended precision as 10 bytes + 6 padding bytes
                    # Use struct to get the double bits, then emit via .quad + .short
                    # For simplicity, store as double precision in 16 bytes
                    # (the x87 will load it correctly via fldl)
                    bits = _struct.unpack('<Q', _struct.pack('<d', val))[0]
                    self._emit(f"  .quad {bits}")
                    self._emit(f"  .quad 0")  # padding to 16 bytes
                elif fp_type == "float":
                    self._emit(f"  .align 4")
                    self._emit(f"{name}:")
                    bits = _struct.unpack('<I', _struct.pack('<f', val))[0]
                    self._emit(f"  .long {bits}")
                else:
                    self._emit(f"  .align 8")
                    self._emit(f"{name}:")
                    bits = _struct.unpack('<Q', _struct.pack('<d', val))[0]
                    self._emit(f"  .quad {bits}")

            # Pointer arrays (e.g. char *arr[] = {"s1", "s2"} or fnptr arrays)
            for gpa in gptrarrs:
                name = (gpa.result or "").lstrip("@")
                meta = gpa.meta or {}
                if gpa.label != "static":
                    self._emit(f".globl {name}")
                self._emit(f"  .align 8")
                self._emit(f"{name}:")
                if "strings" in meta:
                    for s in meta["strings"]:
                        lbl = self._intern_string(s)
                        self._emit(f"  .quad {lbl}")
                elif "symbols" in meta:
                    for sym in meta["symbols"]:
                        self._emit(f"  .quad {sym}")

            # Struct/union member-by-member initialization
            for gs in gstructs:
                name = (gs.result or "").lstrip("@")
                meta = gs.meta or {}
                if gs.label != "static":
                    self._emit(f".globl {name}")
                self._emit(f"  .align 8")
                self._emit(f"{name}:")
                for kind, sz, val in meta.get("members", []):
                    if kind == "zero":
                        self._emit(f"  .zero {sz}")
                    elif kind == "symbol":
                        self._emit(f"  .quad {val}")
                    elif kind == "float":
                        if sz == 4:
                            self._emit(f"  .long {_struct.pack('<f', val).hex()}")
                        elif sz == 8:
                            lo, hi = _struct.unpack('<II', _struct.pack('<d', val))
                            self._emit(f"  .long 0x{lo:08x}")
                            self._emit(f"  .long 0x{hi:08x}")
                        else:
                            self._emit(f"  .zero {sz}")
                    elif kind == "int":
                        if sz == 1:
                            self._emit(f"  .byte {val & 0xFF}")
                        elif sz == 2:
                            self._emit(f"  .short {val & 0xFFFF}")
                        elif sz == 4:
                            self._emit(f"  .long {val & 0xFFFFFFFF}")
                        elif sz == 8:
                            self._emit(f"  .quad {val}")
                        else:
                            self._emit(f"  .zero {sz}")

        # Seed _var_types for local static array symbols so codegen knows to
        # emit leaq (address) instead of movslq (value load).
        for ins in instructions:
            if ins.op == "gdecl" and ins.result and ins.operand1:
                ty = str(ins.operand1)
                if ty.startswith("array(") and ins.result not in self._var_types:
                    self._var_types[ins.result] = ty

        self._emit(".text")
        i = 0
        while i < len(instructions):
            ins = instructions[i]
            if ins.op in {"gdecl", "gdef", "gdef_blob", "gdef_float", "gdef_ptr_array", "gdef_struct"}:
                i += 1
                continue
            if ins.op == "func_begin":
                fn_name = ins.label or ""
                self._fn_name = fn_name
                # Seed return type (if known) for ABI-sensitive `ret`.
                self._fn_ret_ty = ""
                try:
                    if getattr(self, "_sema_ctx", None) is not None and fn_name:
                        fn_ty = getattr(self._sema_ctx, "global_types", {}).get(fn_name)
                        if fn_ty is not None:
                            s = str(fn_ty)
                            if s.startswith("function "):
                                rest = s[len("function ") :].strip()
                                if "(" in rest:
                                    rest = rest.split("(", 1)[0].strip()
                                self._fn_ret_ty = rest
                except Exception:
                    self._fn_ret_ty = ""
                # Seed best-effort type info for temps/symbols used in this function.
                # IR sometimes annotates types via prior "decl" ops for locals,
                # but temps like %t0 (from addr_index) may never appear in decls.
                j = i + 1
                while j < len(instructions) and instructions[j].op != "func_end":
                    d = instructions[j]
                    if d.op == "decl" and d.result and d.operand1:
                        self._var_types[d.result] = str(d.operand1)
                    # If the IR uses a temp as the result of addr_index, it is a pointer value.
                    if d.op == "addr_index" and d.result:
                        # IR lowering may annotate the temp type in sema_ctx-like tables
                        # (CodeGenerator only sees the IR list). Only default to "ptr" when
                        # we have no type for it.
                        if d.result not in self._var_types:
                            self._var_types[d.result] = "ptr"
                    # If the IR uses a temp as the result of addr_of_member, it is a pointer value.
                    if d.op == "addr_of_member" and d.result:
                        if d.result not in self._var_types:
                            mty = (d.meta or {}).get("member_type")
                            self._var_types[d.result] = f"{mty}*" if mty else "ptr"
                    # Propagate best-effort result type for temps produced by load_index.
                    # IRGenerator annotates element type via ins.meta["result_ty"].
                    if d.op == "load_index" and d.result:
                        try:
                            if isinstance(d.meta, dict) and "result_ty" in d.meta and d.result not in self._var_types:
                                self._var_types[d.result] = str(d.meta["result_ty"])
                        except Exception:
                            pass
                    j += 1
                # collect decls/params (and optional func_ret marker) until the
                # first non-prologue instruction. IR commonly emits:
                #   func_begin
                #   func_ret
                #   param...
                # so we must skip func_ret when building the prologue decl list.
                #
                # IMPORTANT: collect ALL decl/param instructions in the entire
                # function body (up to func_end), not just the ones at the top.
                # C89/C99 allows declarations after statements, and the IR
                # generator emits decl instructions at the point of declaration.
                # If we only collect top-of-function decls, later struct locals
                # get allocated via _ensure_local's late-local path which places
                # them after the 4KB spill area, causing stack frame corruption.
                body_start = i + 1
                decls: List[IRInstruction] = []
                # Skip initial prologue-only instructions (func_ret, param, decl)
                # to find where the body starts for code emission.
                prologue_end = body_start
                while prologue_end < len(instructions) and instructions[prologue_end].op in {"decl", "param", "func_ret"}:
                    if instructions[prologue_end].op in {"decl", "param"}:
                        decls.append(instructions[prologue_end])
                    elif instructions[prologue_end].op == "func_ret":
                        self._fn_ret_ty = instructions[prologue_end].operand1 or ""
                    prologue_end += 1
                # Now scan the rest of the function body for additional decls.
                scan = prologue_end
                while scan < len(instructions) and instructions[scan].op != "func_end":
                    if instructions[scan].op in {"decl", "param"}:
                        decls.append(instructions[scan])
                    scan += 1
                body_start = prologue_end

                # Compute stack frame layout for locals/params
                # Reserve a fixed spill area for lazily-created temporaries.
                # This avoids emitting `subq $8, %rsp` for every new %t temp.
                # Keep it 16B-aligned so call-site alignment stays stable.
                self._spill_capacity = 4096
                if self._spill_capacity % 16 != 0:
                    self._spill_capacity += 16 - (self._spill_capacity % 16)
                self._spill_used = 0

                self._begin_function(fn_name, decls)

                i = body_start
                continue

            if ins.op == "func_ret":
                # Per-function return type hint from IR.
                self._fn_ret_ty = (ins.operand1 or "")
                i += 1
                continue

            if ins.op == "func_end":
                # function epilogue already emitted on ret; emit a safety label
                self._fn_name = None
                self._fn_ret_ty = ""
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
                # Keep type info in sync for decls emitted after prologue scan
                # (e.g. local `char s[] = "..."` lowers by overriding decl).
                if ins.operand1:
                    self._var_types[ins.result] = str(ins.operand1)
                    # If an array decl is introduced late, remember its size so
                    # later stack addressing and array decay behaves consistently.
                    op1 = str(ins.operand1)
                    if op1.strip().startswith("array("):
                        enc = op1.strip()
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
                        self._arrays[ins.result] = max(0, elems) * elem_sz
                i += 1
                continue
            self._emit_ins(ins)
            i += 1

        # Emit rodata for strings
        if self._string_pool or self._float_pool:
            self._emit(".section .rodata")
            for s, lbl in self._string_pool.items():
                self._emit(f"{lbl}:")
                self._emit(f"  .string {self._gas_escape(s)}")
            # Emit float constants
            for key, lbl in self._float_pool.items():
                fp_type, bits_hex = key.split(":", 1)
                raw = bytes.fromhex(bits_hex)
                if fp_type == "float":
                    self._emit(f"  .align 4")
                    self._emit(f"{lbl}:")
                    val = _struct.unpack('<I', raw)[0]
                    self._emit(f"  .long {val}")
                else:
                    self._emit(f"  .align 8")
                    self._emit(f"{lbl}:")
                    val = _struct.unpack('<Q', raw)[0]
                    self._emit(f"  .quad {val}")

        return "\n".join(self.assembly_lines) + "\n"

    def _is_local(self, sym: str) -> bool:
        # Treat IR locals ("@x") as local even if they weren't part of the
        # initial decl list, because IR lowering may introduce decls after
        # the prologue scan.
        return sym in self._locals

    def _resolve_member_offset(self, base: str, member: str) -> int:
        """Resolve struct/union member offset in bytes.

        Prefers semantic layout (sema_ctx.layouts) when available; falls back to
        per-function discovered offsets map.
        """

        # First try semantic layouts using base type info.
        ty = self._var_types.get(base)
        if isinstance(ty, str) and ty.strip().endswith("*"):
            ty = ty.strip()[:-1].strip()
        if (ty is None or ty == "") and isinstance(base, str) and base.startswith("@") and self._sema_ctx is not None:
            ty = getattr(self._sema_ctx, "global_types", {}).get(base[1:], None)

        # If `base` is a temp pointer (e.g. from addr_of_member), fall back to
        # its recorded type.
        if (ty is None or ty == "") and isinstance(base, str) and base.startswith("%t"):
            ty = self._var_types.get(base)
            if isinstance(ty, str) and ty.strip().endswith("*"):
                ty = ty.strip()[:-1].strip()

        if isinstance(ty, str) and self._sema_ctx is not None:
            resolved_ty = self._resolve_type(ty)
            layout = getattr(self._sema_ctx, "layouts", {}).get(resolved_ty)
            if layout is not None:
                off = layout.member_offsets.get(member)
                if isinstance(off, int):
                    return off

        # Fall back to per-function cached offsets.
        off2 = self._member_offsets.get((base, member))
        if isinstance(off2, int):
            return off2
        return 0

    def _resolve_member_type(self, base: str, member: str) -> Optional[str]:
        """Best-effort resolve the declared type of a struct/union member.

        Uses semantic information (sema_ctx.layouts + sema_ctx.global_types) to
        determine whether a byte-sized member is `signed char` vs `unsigned char`
        or plain `char`.

        Returns a type string (e.g. "signed char") or None.
        """

        if self._sema_ctx is None:
            return None

        ty = self._var_types.get(base)
        if isinstance(ty, str) and ty.strip().endswith("*"):
            ty = ty.strip()[:-1].strip()
        if (ty is None or ty == "") and isinstance(base, str) and base.startswith("@"):
            ty = getattr(self._sema_ctx, "global_types", {}).get(base[1:], None)
        # If `base` is a temp holding a pointer into a struct/union (e.g. result
        # of addr_of_member/addr_of_member_ptr), consult its recorded type.
        # Those are stored as "<ty>*" in `_var_types`.
        if (ty is None or ty == "") and isinstance(base, str) and base.startswith("%t"):
            ty = self._var_types.get(base)
            if isinstance(ty, str) and ty.strip().endswith("*"):
                ty = ty.strip()[:-1].strip()

        if not isinstance(ty, str) or not ty:
            return None

        resolved_ty = self._resolve_type(ty)
        layout = getattr(self._sema_ctx, "layouts", {}).get(resolved_ty)
        if layout is None:
            return None

        mtypes = getattr(layout, "member_types", None)
        if isinstance(mtypes, dict):
            mt = mtypes.get(member)
            if isinstance(mt, str):
                return mt
        return None

    # Function framing

    def _begin_function(self, name: str, decls: List[IRInstruction]) -> None:
        self._locals = {}
        self._arrays = {}
        self._member_offsets = {}
        # `_var_types` is initialized once per `generate()` call.
        # Stack frame invariant:
        # - declared locals are assigned fixed slots first
        # - a fixed spill region for IR temps (%t*) is reserved below locals
        # - any late-discovered locals are allocated below the spill region
        #
        # `_spill_capacity/_spill_used` are initialized in `generate()` for each
        # function; do not reset them here.

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
                # Struct/union locals: allocate actual size, at least 8 bytes for alignment.
                ty_str = str(d.operand1) if d.operand1 else ""
                resolved_ty = self._resolve_type(ty_str)
                if resolved_ty.startswith("struct ") or resolved_ty.startswith("union "):
                    size_bytes = self._type_size_bytes(resolved_ty)
                    # Round up to multiple of 8 so register-chunk stores don't overflow.
                    size_bytes = ((size_bytes + 7) // 8) * 8
                    size_bytes = max(size_bytes, 8)
                    offset += size_bytes
                    self._locals[sym] = offset
                    self._var_types[sym] = resolved_ty
                elif ty_str.strip() == "long double":
                    # long double needs 16-byte aligned slot (x86-64 ABI)
                    # Align offset to 16-byte boundary first
                    if offset % 16 != 0:
                        offset += 16 - (offset % 16)
                    offset += 16
                    self._locals[sym] = offset
                    self._var_types[sym] = "long double"
                else:
                    # Scalar locals: reserve a full 8-byte slot (simplifies addressing).
                    offset += 8
                    self._locals[sym] = offset
                    if d.operand1:
                        # remember declared type base for load/store width decisions
                        self._var_types[sym] = str(d.operand1)

        # Seed stack slots for late-discovered locals.
        # IR currently emits decls before first use, but codegen also allocates
        # stack slots lazily when it sees new symbols. Many such symbols are
        # actually user locals (not temps), and we must not adjust %rsp during
        # the function body.
        for d in decls:
            if d.op != "decl" or not d.result:
                continue
            sym = d.result
            if sym in self._locals:
                continue
            offset += 8
            self._locals[sym] = offset
            if d.operand1:
                self._var_types[sym] = str(d.operand1)

        # Record declared locals size *before* reserving the spill area.
        # Offsets in self._locals are positive and used as -off(%rbp).
        self._locals_base = max(self._locals.values()) if self._locals else 0

        # Fixed spill area reserved for temporaries lives below declared locals.
        offset += self._spill_capacity

        # Align stack to 16 bytes (SysV ABI requirement for call sites).
        # After push %rbp, %rsp is 16-aligned. subq $N must keep it aligned.
        stack = offset
        if stack % 16 != 0:
            stack += 16 - (stack % 16)
        self._stack_size = stack

        # IR may tag internal-linkage functions as "name@static".
        emit_name = name
        is_static_fn = False
        if isinstance(name, str) and name.endswith("@static"):
            emit_name = name[: -len("@static")]
            is_static_fn = True

        if not is_static_fn:
            self._emit(f".globl {emit_name}")
        self._emit(f"{emit_name}:")
        self._emit("  pushq %rbp")
        self._emit("  movq %rsp, %rbp")
        if self._stack_size:
            self._emit(f"  subq ${self._stack_size}, %rsp")
        # Maintain SysV ABI stack alignment at call sites.
        # After `call`, %rsp is 8 mod 16 on entry. After `push %rbp`, %rsp is 0 mod 16.
        # Subtracting an aligned frame keeps it aligned here, but any subsequent pushes
        # must be paired so that %rsp is again 0 mod 16 right before a `call`.
        self._call_stack_adjust = 0

        # SysV ABI: if this function returns a MEMORY-class struct, the caller
        # passes a hidden pointer via %rdi as the implicit first argument.
        # Save it now before processing explicit parameters.
        self._hidden_ret_ptr_off = 0
        ret_ty = getattr(self, "_fn_ret_ty", "") or ""
        if isinstance(ret_ty, str) and (ret_ty.strip().startswith("struct ") or ret_ty.strip().startswith("union ")):
            rty_s = ret_ty.strip()
            layout = getattr(self._sema_ctx, "layouts", {}).get(rty_s) if self._sema_ctx else None
            classification = classify_struct(rty_s, layout) if layout else [EightbyteClass.INTEGER]
            pm = get_struct_pass_mode(classification)
            if pm == "hidden_ptr":
                # Save the hidden pointer (%rdi) into a spill slot.
                tmp = self._new_spill_name()
                self._hidden_ret_ptr_off = self._ensure_local(tmp)
                self._emit(f"  movq %rdi, -{self._hidden_ret_ptr_off}(%rbp)")

        # Move params from registers into stack slots (treat @param as local)
        arg_regs = ["%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"]
        xmm_arg_regs = ["%xmm0", "%xmm1", "%xmm2", "%xmm3", "%xmm4", "%xmm5", "%xmm6", "%xmm7"]
        gp_idx = 0
        xmm_idx = 0
        stack_arg_off = 0  # offset for stack-passed params (e.g. long double)
        # If we consumed %rdi for the hidden return pointer, skip it.
        if self._hidden_ret_ptr_off:
            gp_idx = 1
        for d in decls:
            if d.op != "param" or not d.result:
                continue
            ty = str(d.operand1 or "").strip()
            off = self._locals.get(d.result)
            if off is None:
                if ty == "long double":
                    # long double params are passed on the stack (MEMORY class)
                    # but no local slot allocated — just skip and advance stack offset
                    stack_arg_off += 16
                elif ty in ("float", "double"):
                    xmm_idx += 1
                else:
                    gp_idx += 1
                continue
            if ty == "long double":
                # SysV ABI: long double is MEMORY class, passed on the stack.
                # Copy from caller's stack frame into local slot.
                # Stack args start at 16(%rbp): 0(%rbp)=saved rbp, 8(%rbp)=ret addr
                self._emit(f"  movq {16 + stack_arg_off}(%rbp), %rax")
                self._emit(f"  movq %rax, -{off}(%rbp)")
                self._emit(f"  movq {16 + stack_arg_off + 8}(%rbp), %rax")
                self._emit(f"  movq %rax, -{off - 8}(%rbp)")
                self._var_types[d.result] = "long double"
                stack_arg_off += 16
            elif ty in ("float", "double"):
                if xmm_idx < len(xmm_arg_regs):
                    s = "s" if ty == "float" else "d"
                    self._emit(f"  movs{s} {xmm_arg_regs[xmm_idx]}, -{off}(%rbp)")
                xmm_idx += 1
            elif ty.startswith("struct ") or ty.startswith("union "):
                # Struct/union by-value param: use StructClassifier to decide
                # GP vs XMM registers per eightbyte (SysV ABI).
                layout = getattr(self._sema_ctx, "layouts", {}).get(ty) if self._sema_ctx else None
                classification = classify_struct(ty, layout) if layout else [EightbyteClass.INTEGER]
                pass_mode = get_struct_pass_mode(classification)
                sz = self._type_size_bytes(ty)

                if pass_mode == "hidden_ptr":
                    # Large struct (>16 bytes): passed via hidden pointer in
                    # next GP register.  Copy the pointed-to data into the
                    # local stack slot.
                    if gp_idx < len(arg_regs):
                        src_reg = arg_regs[gp_idx]
                        gp_idx += 1
                        # Copy sz bytes from src_reg into local slot at -off(%rbp).
                        # Use rep movsb for simplicity.
                        self._emit(f"  movq {src_reg}, %rsi")
                        self._emit(f"  leaq -{off}(%rbp), %rdi")
                        self._emit(f"  movq ${sz}, %rcx")
                        self._emit("  rep movsb")
                elif pass_mode == "registers":
                    # Check if we have enough registers for all eightbytes.
                    gp_needed = sum(1 for c in classification if c == EightbyteClass.INTEGER)
                    sse_needed = sum(1 for c in classification if c == EightbyteClass.SSE)
                    if gp_idx + gp_needed <= len(arg_regs) and xmm_idx + sse_needed <= len(xmm_arg_regs):
                        # Enough registers: store each eightbyte from the
                        # appropriate register type.
                        for ci, cls in enumerate(classification):
                            if cls == EightbyteClass.SSE:
                                self._emit(f"  movq {xmm_arg_regs[xmm_idx]}, -{off - ci * 8}(%rbp)")
                                xmm_idx += 1
                            else:
                                # INTEGER (or NO_CLASS treated as INTEGER)
                                self._emit(f"  movq {arg_regs[gp_idx]}, -{off - ci * 8}(%rbp)")
                                gp_idx += 1
                    else:
                        # Not enough registers: entire struct was passed on
                        # the stack by the caller.  The struct data lives at
                        # a positive offset from %rbp (above the return
                        # address).  We reconstruct it into the local slot.
                        # NOTE: for the callee prologue, stack-passed struct
                        # params are handled by the existing stack arg
                        # mechanism; we just consume the GP/XMM slots that
                        # *would* have been used so subsequent params get
                        # correct register indices.
                        chunks = (sz + 7) // 8
                        for ci in range(chunks):
                            if gp_idx < len(arg_regs):
                                self._emit(f"  movq {arg_regs[gp_idx]}, -{off - ci * 8}(%rbp)")
                                gp_idx += 1
                else:
                    # Fallback: stack-passed struct.  Same as register
                    # exhaustion case above.
                    chunks = (sz + 7) // 8
                    for ci in range(chunks):
                        if gp_idx < len(arg_regs):
                            self._emit(f"  movq {arg_regs[gp_idx]}, -{off - ci * 8}(%rbp)")
                            gp_idx += 1
            else:
                if gp_idx < len(arg_regs):
                    if ty == "char" or ty == "unsigned char":
                        r = arg_regs[gp_idx]
                        breg = {"%rdi": "%dil", "%rsi": "%sil", "%rdx": "%dl", "%rcx": "%cl", "%r8": "%r8b", "%r9": "%r9b"}.get(r, "%dil")
                        self._emit(f"  movb {breg}, -{off}(%rbp)")
                    elif ty in ("short", "short int", "unsigned short"):
                        r = arg_regs[gp_idx]
                        w = {"%rdi": "%di", "%rsi": "%si", "%rdx": "%dx", "%rcx": "%cx", "%r8": "%r8w", "%r9": "%r9w"}.get(r, "%di")
                        self._emit(f"  movw {w}, -{off}(%rbp)")
                    elif ty in ("int", "unsigned int") or ty.startswith("enum "):
                        r = arg_regs[gp_idx]
                        l = {"%rdi": "%edi", "%rsi": "%esi", "%rdx": "%edx", "%rcx": "%ecx", "%r8": "%r8d", "%r9": "%r9d"}.get(r, "%edi")
                        self._emit(f"  movl {l}, -{off}(%rbp)")
                    else:
                        self._emit(f"  movq {arg_regs[gp_idx]}, -{off}(%rbp)")
                gp_idx += 1
            if d.operand1:
                self._var_types[d.result] = str(d.operand1)

        # Varargs support (SysV AMD64): reserve a fixed reg_save_area and tag
        # area in the callee frame so `__builtin_va_start` can produce a glibc
        # ABI-compatible `va_list`.
        #
        # SysV glibc expects `va_list.reg_save_area` to reference a 176-byte
        # reg_save_area:
        #   - GP save area: 6 * 8 bytes for rdi..r9 (48 bytes)
        #   - FP save area: 8 * 16 bytes for xmm0..xmm7 (128 bytes)
        #
        # The critical part for our milestone is the GP save area.
        self._varargs_reg_save_base = None  # offset of start of 176B area
        self._varargs_tag_base = None  # offset of start of 32B tag area
        self._varargs_named_gpr_count = 0

        is_variadic = any((d.op == "param" and (d.result or "").lstrip("@") == "...") for d in decls)

        if is_variadic:
            # Reserve fixed ABI areas at the very bottom of the frame so that
            # later local/temp allocation cannot overlap them.
            #
            # Layout (lowest addresses):
            #   [reg_save_area 176B] [tag area 32B]
            # Both are addressed via fixed -off(%rbp) offsets.
            abi_reserve = self._VARARGS_VA_LIST_TAG_AREA_SIZE + self._VARARGS_REG_SAVE_AREA_SIZE
            # keep 16B alignment
            if abi_reserve % 16 != 0:
                abi_reserve += 16 - (abi_reserve % 16)
            self._stack_size += abi_reserve

            # Patch already-emitted prologue to use the final frame size.
            for idx, line in enumerate(self.assembly_lines[:16]):
                if line.strip().startswith("subq $") and line.strip().endswith(", %rsp"):
                    self.assembly_lines[idx] = f"  subq ${self._stack_size}, %rsp"
                    break

            # ABI region lives at the very bottom of the frame and is addressed
            # via fixed -off(%rbp) offsets (so later spills cannot overlap it).
            #
            # Invariants (all offsets are positive integers used as -off(%rbp)):
            #   reg_save_area_addr = rbp - _varargs_reg_save_base
            #   tag_addr           = rbp - _varargs_tag_base
            #   tag_addr           = reg_save_area_addr - _VARARGS_REG_SAVE_AREA_SIZE
            #
            # `reg_save_area` begins with the 48-byte GP slots (rdi..r9).
            self._varargs_reg_save_base = int(self._stack_size - self._VARARGS_GP_SAVE_AREA_SIZE)
            self._varargs_tag_base = int(self._stack_size - self._VARARGS_GP_SAVE_AREA_SIZE - self._VARARGS_REG_SAVE_AREA_SIZE)

            # Count named GP params (excluding the '...').
            self._varargs_named_gpr_count = 0
            for d in decls:
                if d.op != "param" or not d.result:
                    continue
                nm = (d.result or "").lstrip("@")
                if nm == "...":
                    break
                self._varargs_named_gpr_count += 1

            base = self._varargs_reg_save_base
            # Save *incoming* regs immediately in the prologue, before we use
            # any of them as scratch.
            # Layout: reg_save_area[0]=rdi, [8]=rsi, [16]=rdx, [24]=rcx, [32]=r8, [40]=r9
            # We store them so that reg_save_area points to rdi and higher
            # offsets correspond to later registers (ascending address order).
            self._emit(f"  movq %rdi, -{base + 40}(%rbp)")
            self._emit(f"  movq %rsi, -{base + 32}(%rbp)")
            self._emit(f"  movq %rdx, -{base + 24}(%rbp)")
            self._emit(f"  movq %rcx, -{base + 16}(%rbp)")
            self._emit(f"  movq %r8,  -{base + 8}(%rbp)")
            self._emit(f"  movq %r9,  -{base + 0}(%rbp)")

        
    # Instruction emission

    def _emit_ins(self, ins: IRInstruction) -> None:
        op = ins.op
        if op == "label":
            self._emit(f"{ins.label}:")
            return

        # NOTE: Don't blindly rewrite bare identifiers to '@name' here.
        # Bare identifiers may legally be extern/global symbols or macro
        # expanded string-literals (e.g. NAME -> "ok"). Params/locals should
        # already be '@name' once prologue scanning assigns stack slots.
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
            # Volatile annotation: mark memory accesses for volatile-qualified
            # variables so they are never optimised away.
            _is_volatile_mov = bool(ins.meta and ins.meta.get("volatile"))
            # Float-aware move: if source is a float-typed temp, use SSE move
            src_ty = self._var_types.get(ins.operand1, "")
            if isinstance(src_ty, str) and src_ty in ("float", "double"):
                s = "s" if src_ty == "float" else "d"
                mov = f"movs{s}"
                off1 = self._ensure_local(ins.operand1)
                if _is_volatile_mov:
                    self._emit(f"  {mov} -{off1}(%rbp), %xmm0  # volatile load")
                else:
                    self._emit(f"  {mov} -{off1}(%rbp), %xmm0")
                off_r = self._ensure_local(ins.result)
                if _is_volatile_mov:
                    self._emit(f"  {mov} %xmm0, -{off_r}(%rbp)  # volatile store")
                else:
                    self._emit(f"  {mov} %xmm0, -{off_r}(%rbp)")
                # Propagate float type
                self._var_types[ins.result] = src_ty
                return
            if _is_volatile_mov:
                self._emit("  # volatile")
            self._load_operand(ins.operand1, "%rax")
            self._store_result(ins.result, "%rax")
            try:
                if ins.operand1 is not None:
                    step = self._ptr_step_bytes.get(str(ins.operand1))
                    if step is not None and ins.result is not None:
                        self._ptr_step_bytes[str(ins.result)] = int(step)
            except Exception:
                pass
            return

        if op == "struct_copy":
            sz = (ins.meta or {}).get("size", 0)
            if sz > 0:
                src_off = self._ensure_local(ins.operand1)
                dst_off = self._ensure_local(ins.result)
                self._emit(f"  leaq -{src_off}(%rbp), %rsi")
                self._emit(f"  leaq -{dst_off}(%rbp), %rdi")
                self._emit(f"  movq ${sz}, %rcx")
                self._emit(f"  rep movsb")
            return

        if op == "fmov":
            fp_type = (ins.meta or {}).get("fp_type", "double")
            if fp_type == "long double":
                # x87 long double: load constant via memory (use double approximation,
                # then store as 80-bit extended via x87 stack)
                val_str = ins.operand1 or "0.0"
                lbl = self._intern_float_literal(float(val_str), "double")
                # Load double constant into x87 stack, then store as 80-bit tbyte
                self._emit(f"  fldl {lbl}(%rip)")
                if ins.result:
                    off = self._ensure_local(ins.result, size=16)
                    self._emit(f"  fstpt -{off}(%rbp)")
                    self._var_types[ins.result] = "long double"
                else:
                    # Pop x87 stack if no result
                    self._emit("  fstp %st(0)")
                return
            val_str = ins.operand1 or "0.0"
            lbl = self._intern_float_literal(float(val_str), fp_type)
            if fp_type == "float":
                self._emit(f"  movss {lbl}(%rip), %xmm0")
            else:
                self._emit(f"  movsd {lbl}(%rip), %xmm0")
            if ins.result:
                off = self._ensure_local(ins.result)
                if fp_type == "float":
                    self._emit(f"  movss %xmm0, -{off}(%rbp)")
                else:
                    self._emit(f"  movsd %xmm0, -{off}(%rbp)")
                self._var_types[ins.result] = fp_type
            return

        if op in ("fadd", "fsub", "fmul", "fdiv"):
            fp_type = (ins.meta or {}).get("fp_type", "double")
            if fp_type == "long double":
                # x87 long double arithmetic
                off1 = self._ensure_local(ins.operand1, size=16)
                off2 = self._ensure_local(ins.operand2, size=16)
                # Load first operand, then second operand onto x87 stack
                self._emit(f"  fldt -{off1}(%rbp)")
                self._emit(f"  fldt -{off2}(%rbp)")
                # Perform operation: st(1) op st(0), pop
                # Note: fsubrp/fdivrp for correct operand order (a - b, a / b)
                x87_ops = {"fadd": "faddp", "fsub": "fsubrp",
                           "fmul": "fmulp", "fdiv": "fdivrp"}
                self._emit(f"  {x87_ops[op]} %st(0), %st(1)")
                # Store result from x87 stack
                off_r = self._ensure_local(ins.result, size=16)
                self._emit(f"  fstpt -{off_r}(%rbp)")
                self._var_types[ins.result] = "long double"
                return
            s = "s" if fp_type == "float" else "d"
            mov = f"movs{s}"
            off1 = self._ensure_local(ins.operand1)
            self._emit(f"  {mov} -{off1}(%rbp), %xmm0")
            off2 = self._ensure_local(ins.operand2)
            self._emit(f"  {mov} -{off2}(%rbp), %xmm1")
            sse_ops = {"fadd": f"adds{s}", "fsub": f"subs{s}",
                       "fmul": f"muls{s}", "fdiv": f"divs{s}"}
            self._emit(f"  {sse_ops[op]} %xmm1, %xmm0")
            off_r = self._ensure_local(ins.result)
            self._emit(f"  {mov} %xmm0, -{off_r}(%rbp)")
            self._var_types[ins.result] = fp_type
            return

        if op == "fcmp":
            fp_type = (ins.meta or {}).get("fp_type", "double")
            if fp_type == "long double":
                # x87 long double comparison using fcomip
                off1 = self._ensure_local(ins.operand1, size=16)
                off2 = self._ensure_local(ins.operand2, size=16)
                # Load operands: first load b (operand2), then a (operand1)
                # so a is in st(0) and b is in st(1)
                self._emit(f"  fldt -{off2}(%rbp)")
                self._emit(f"  fldt -{off1}(%rbp)")
                # fcomip compares st(0) with st(1), sets EFLAGS, pops st(0)
                self._emit("  fcomip %st(1), %st(0)")
                # Pop remaining st(0) (was st(1))
                self._emit("  fstp %st(0)")
                cmp_op = ins.label or "<"
                set_map = {"<": "setb", "<=": "setbe", ">": "seta", ">=": "setae",
                           "==": "sete", "!=": "setne"}
                self._emit(f"  {set_map.get(cmp_op, 'setb')} %al")
                self._emit("  movzbl %al, %eax")
                self._emit("  movslq %eax, %rax")
                self._store_result(ins.result, "%rax")
                return
            s = "s" if fp_type == "float" else "d"
            mov = f"movs{s}"
            off1 = self._ensure_local(ins.operand1)
            self._emit(f"  {mov} -{off1}(%rbp), %xmm0")
            off2 = self._ensure_local(ins.operand2)
            self._emit(f"  {mov} -{off2}(%rbp), %xmm1")
            self._emit(f"  ucomis{s} %xmm1, %xmm0")
            cmp_op = ins.label or "<"
            set_map = {"<": "setb", "<=": "setbe", ">": "seta", ">=": "setae",
                       "==": "sete", "!=": "setne"}
            self._emit(f"  {set_map.get(cmp_op, 'setb')} %al")
            self._emit("  movzbl %al, %eax")
            self._emit("  movslq %eax, %rax")
            self._store_result(ins.result, "%rax")
            return

        if op in ("i2f", "i2d"):
            fp_type = (ins.meta or {}).get("fp_type", "double")
            self._load_operand(ins.operand1, "%rax")
            if fp_type == "float":
                self._emit("  cvtsi2ssl %eax, %xmm0")
                off_r = self._ensure_local(ins.result)
                self._emit(f"  movss %xmm0, -{off_r}(%rbp)")
            else:
                self._emit("  cvtsi2sdq %rax, %xmm0")
                off_r = self._ensure_local(ins.result)
                self._emit(f"  movsd %xmm0, -{off_r}(%rbp)")
            self._var_types[ins.result] = fp_type
            return

        if op in ("f2i", "d2i"):
            fp_type = (ins.meta or {}).get("fp_type", "float" if op == "f2i" else "double")
            src = ins.operand1 or ""
            if src.startswith("@") and not self._is_local(src):
                gname = src.lstrip("@")
                if fp_type == "float":
                    self._emit(f"  movss {gname}(%rip), %xmm0")
                else:
                    self._emit(f"  movsd {gname}(%rip), %xmm0")
            else:
                off1 = self._ensure_local(src)
                if fp_type == "float":
                    self._emit(f"  movss -{off1}(%rbp), %xmm0")
                else:
                    self._emit(f"  movsd -{off1}(%rbp), %xmm0")
            if fp_type == "float":
                self._emit("  cvttss2si %xmm0, %eax")
            else:
                self._emit("  cvttsd2si %xmm0, %rax")
            self._emit("  cltq")
            self._store_result(ins.result, "%rax")
            return

        if op == "f2d":
            off1 = self._ensure_local(ins.operand1)
            self._emit(f"  movss -{off1}(%rbp), %xmm0")
            self._emit("  cvtss2sd %xmm0, %xmm0")
            off_r = self._ensure_local(ins.result)
            self._emit(f"  movsd %xmm0, -{off_r}(%rbp)")
            return

        if op == "d2f":
            off1 = self._ensure_local(ins.operand1)
            self._emit(f"  movsd -{off1}(%rbp), %xmm0")
            self._emit("  cvtsd2ss %xmm0, %xmm0")
            off_r = self._ensure_local(ins.result)
            self._emit(f"  movss %xmm0, -{off_r}(%rbp)")
            return

        # --- long double (x87) conversion ops ---

        if op == "i2ld":
            # int → long double: push int to memory, use fildq, store as tbyte
            self._load_operand(ins.operand1, "%rax")
            # Store int to a temp memory slot for fild
            tmp_off = self._ensure_local(self._new_spill_name())
            self._emit(f"  movq %rax, -{tmp_off}(%rbp)")
            self._emit(f"  fildq -{tmp_off}(%rbp)")
            off_r = self._ensure_local(ins.result, size=16)
            self._emit(f"  fstpt -{off_r}(%rbp)")
            self._var_types[ins.result] = "long double"
            return

        if op == "ld2i":
            # long double → int: load tbyte, use fistp to convert and store
            off1 = self._ensure_local(ins.operand1, size=16)
            self._emit(f"  fldt -{off1}(%rbp)")
            # Use a temp slot for fistp result
            tmp_off = self._ensure_local(self._new_spill_name())
            # Set rounding mode to truncation (like C cast behavior)
            # Save current x87 control word, set truncation mode, fistp, restore
            cw_off = self._ensure_local(self._new_spill_name())
            cw_new_off = self._ensure_local(self._new_spill_name())
            self._emit(f"  fnstcw -{cw_off}(%rbp)")
            self._emit(f"  movw -{cw_off}(%rbp), %ax")
            self._emit("  orw $0x0c00, %ax")  # Set RC=11 (truncate)
            self._emit(f"  movw %ax, -{cw_new_off}(%rbp)")
            self._emit(f"  fldcw -{cw_new_off}(%rbp)")
            self._emit(f"  fistpq -{tmp_off}(%rbp)")
            self._emit(f"  fldcw -{cw_off}(%rbp)")  # Restore original CW
            self._emit(f"  movq -{tmp_off}(%rbp), %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "d2ld":
            # double → long double: load double via fldl, store as tbyte
            off1 = self._ensure_local(ins.operand1)
            self._emit(f"  fldl -{off1}(%rbp)")
            off_r = self._ensure_local(ins.result, size=16)
            self._emit(f"  fstpt -{off_r}(%rbp)")
            self._var_types[ins.result] = "long double"
            return

        if op == "ld2d":
            # long double → double: load tbyte, store as double via fstpl
            off1 = self._ensure_local(ins.operand1, size=16)
            self._emit(f"  fldt -{off1}(%rbp)")
            off_r = self._ensure_local(ins.result)
            self._emit(f"  fstpl -{off_r}(%rbp)")
            self._var_types[ins.result] = "double"
            return

        if op == "f2ld":
            # float → long double: load float via flds, store as tbyte
            off1 = self._ensure_local(ins.operand1)
            self._emit(f"  flds -{off1}(%rbp)")
            off_r = self._ensure_local(ins.result, size=16)
            self._emit(f"  fstpt -{off_r}(%rbp)")
            self._var_types[ins.result] = "long double"
            return

        if op == "ld2f":
            # long double → float: load tbyte, store as float via fstps
            off1 = self._ensure_local(ins.operand1, size=16)
            self._emit(f"  fldt -{off1}(%rbp)")
            off_r = self._ensure_local(ins.result)
            self._emit(f"  fstps -{off_r}(%rbp)")
            self._var_types[ins.result] = "float"
            return

        if op == "sext16":
            # result = sign_extend_16(operand1)
            self._load_operand(ins.operand1, "%rax")
            self._emit("  movswl %ax, %eax")
            self._emit("  movslq %eax, %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "load":
            # result = *(operand1)
            _is_volatile_load = bool(ins.meta and ins.meta.get("volatile"))
            if _is_volatile_load:
                self._emit("  # volatile load")
            # Best-effort: choose width based on pointer pointee type.
            addr = ins.operand1 or ""
            elem_sz = 4
            base_ty = None
            if isinstance(addr, str):
                base_ty = self._var_types.get(addr)
                if base_ty is None and addr.startswith("@") and self._sema_ctx is not None:
                    base_ty = getattr(self._sema_ctx, "global_types", {}).get(addr[1:], None)
                # If this is a temp holding a pointer but we didn't record its
                # type, default to a generic byte pointer so we don't accidentally
                # read 4 bytes (elem_sz=4) for a char dereference.
                if (base_ty is None or base_ty == "") and addr.startswith("%t"):
                    base_ty = "char*"
            if isinstance(base_ty, str) and "*" in base_ty:
                elem_sz = self._pointee_size_bytes(base_ty)

            # If IR provided an explicit load size, prefer it.
            try:
                if isinstance(ins.meta, dict) and "load_size_bytes" in ins.meta:
                    elem_sz = int(ins.meta["load_size_bytes"])
            except Exception:
                pass

            self._load_operand(addr, "%rax")
            if elem_sz == 1:
                if self._pointee_is_unsigned(base_ty):
                    self._emit("  movzbl (%rax), %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  movsbl (%rax), %eax")
                    self._emit("  movslq %eax, %rax")
            elif elem_sz == 2:
                if self._pointee_is_unsigned(base_ty):
                    self._emit("  movzwq (%rax), %rax")
                else:
                    self._emit("  movswq (%rax), %rax")
                # Track loaded value type so later ops (e.g. >>) can choose
                # signed vs unsigned behavior correctly.
                try:
                    if ins.result:
                        self._var_types[ins.result] = "unsigned short" if self._pointee_is_unsigned(base_ty) else "short"
                except Exception:
                    pass
            elif elem_sz == 4:
                # Integer loads must respect signedness of the pointee.
                if self._pointee_is_unsigned(base_ty):
                    self._emit("  movl (%rax), %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  movslq (%rax), %rax")
            else:
                self._emit("  movq (%rax), %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "store":
            # *(operand1) = result
            _is_volatile_store = bool(ins.meta and ins.meta.get("volatile"))
            if _is_volatile_store:
                self._emit("  # volatile store")
            # Best-effort: choose width based on pointer pointee type.
            addr = ins.operand1 or ""
            val = ins.result
            elem_sz = 4
            base_ty = None
            if isinstance(addr, str):
                base_ty = self._var_types.get(addr)
                if base_ty is None and addr.startswith("@") and self._sema_ctx is not None:
                    base_ty = getattr(self._sema_ctx, "global_types", {}).get(addr[1:], None)
            if isinstance(base_ty, str) and "*" in base_ty:
                elem_sz = self._pointee_size_bytes(base_ty)

            self._load_operand(addr, "%rax")
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

        if op == "mov_addr":
            # result = &operand1 (more explicit than addr_of in cases where operand1
            # is an lvalue expression already resolved to a symbol)
            src = ins.operand1 or ""
            self._addr_of_symbol(src, "%rax")
            self._store_result(ins.result, "%rax")
            # Preserve best-effort type info for address temps. IR may annotate
            # such temps in `sema_ctx.var_types` (or rely on generator-side tables),
            # but codegen needs it to choose correct element size in load_index.
            if ins.result and isinstance(src, str):
                ty = self._var_types.get(src)
                if isinstance(ty, str) and ty.strip().startswith("array("):
                    inner = ty.strip()[len("array(") :]
                    if inner.endswith(")"):
                        inner = inner[:-1]
                    base_part = inner.split(",", 1)[0].strip()
                    self._var_types[ins.result] = f"{base_part}*"
            # Carry optional pointer arithmetic scaling overrides (e.g. decay of
            # multi-dimensional arrays to pointer-to-row).
            try:
                if ins.result and isinstance(ins.meta, dict) and "ptr_step_bytes" in ins.meta:
                    self._ptr_step_bytes[ins.result] = int(ins.meta["ptr_step_bytes"])
            except Exception:
                pass
            return

        if op == "addr_index":
            # result = &base[idx]
            base = ins.operand1 or ""
            idx = ins.operand2 or "$0"

            # Prefer any existing type info for the base temp/symbol.
            base_ty = self._var_types.get(base, "")
            if (base_ty is None or base_ty == "") and isinstance(base, str) and base.startswith("@") and self._sema_ctx is not None:
                base_ty = getattr(self._sema_ctx, "global_types", {}).get(base[1:], "")

            # If base is a temp holding a pointer, use the pointee type to size elements.
            if (base_ty is None or base_ty == "") and isinstance(base, str) and base.startswith("%t"):
                base_ty = self._var_types.get(base, "")
            elem_sz = 4
            step_override = None
            try:
                if isinstance(ins.meta, dict) and "ptr_step_bytes" in ins.meta:
                    step_override = int(ins.meta["ptr_step_bytes"])
                else:
                    step_override = self._ptr_step_bytes.get(str(base))
            except Exception:
                step_override = None
            if isinstance(base_ty, str) and "*" in base_ty:
                elem_sz = self._pointee_size_bytes(base_ty)
            elif isinstance(base_ty, str) and base_ty.strip().startswith("array("):
                inner = base_ty.strip()[len("array(") :]
                if inner.endswith(")"):
                    inner = inner[:-1]
                base_part = inner.split(",", 1)[0].strip()
                elem_sz = self._type_size_bytes(base_part)
            elif isinstance(base_ty, str) and (base_ty.startswith("struct ") or base_ty.startswith("union ")):
                # Unsized arrays like `struct S arr[] = {...}` are recorded in
                # global_types as just "struct S".
                elem_sz = self._type_size_bytes(base_ty)

            # base address
            is_ptr_base = (isinstance(base_ty, str) and "*" in base_ty) or (isinstance(base, str) and base.startswith("%t"))
            if is_ptr_base:
                self._load_operand(base, "%rax")
            else:
                self._addr_of_symbol(base, "%rax")
            self._load_operand(idx, "%rcx")
            # Multi-dimensional arrays: when IR provides an explicit step,
            # that value is already a byte stride. Use it directly as the
            # scaling factor (do not apply another element-size scaling).
            if isinstance(step_override, int) and step_override > 0:
                elem_sz = int(step_override)
            if elem_sz != 1:
                self._emit(f"  imulq ${elem_sz}, %rcx")
            self._emit("  addq %rcx, %rax")
            self._store_result(ins.result, "%rax")
            # Best-effort: record that the resulting temp holds an address.
            if ins.result and isinstance(ins.result, str) and ins.result.startswith("%t"):
                # If IR already knows the result temp's type (e.g. "struct S*"), keep it.
                existing = self._var_types.get(ins.result, "")
                if not (isinstance(existing, str) and "*" in existing):
                    if isinstance(base_ty, str) and (base_ty.startswith("struct ") or base_ty.startswith("union ")):
                        self._var_types[ins.result] = f"{base_ty}*"
                    elif isinstance(base_ty, str) and base_ty.strip().startswith("array("):
                        enc = base_ty.strip()
                        inner = enc[len("array(") :]
                        if inner.endswith(")"):
                            inner = inner[:-1]
                        elem_ty = inner.split(",", 1)[0].strip()
                        self._var_types[ins.result] = f"{elem_ty}*"
                    else:
                        self._var_types[ins.result] = "ptr"
            # Carry optional pointer arithmetic scaling overrides (bytes).
            # This is used for row pointers produced by multi-dimensional array
            # indexing lowerings.
            try:
                if ins.result and isinstance(ins.meta, dict) and "ptr_step_bytes" in ins.meta:
                    self._ptr_step_bytes[str(ins.result)] = int(ins.meta["ptr_step_bytes"])
            except Exception:
                pass
            return

        if op == "addr_of_member":
            # result = &operand1.member
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            # Load base address into %rax then add member offset.
            # IMPORTANT: `base` is an lvalue (struct/union object). We must take
            # its address rather than load its value.
            base_ty = self._var_types.get(base, "")
            if isinstance(base, str) and base.startswith("%t") and isinstance(base_ty, str) and (base_ty.strip().endswith("*") or base_ty.strip() == "ptr"):
                # addr_of_member can be used on a temp that already is a pointer
                # to a struct/union object (e.g. when rewriting `s.b` as an
                # lvalue address). In that case, load the pointer value.
                self._load_operand(base, "%rax")
            else:
                self._addr_of_symbol(base, "%rax")
            off = self._resolve_member_offset(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            self._store_result(ins.result, "%rax")
            # best-effort propagate pointer type: if base is a struct/union symbol,
            # treat result as pointer-to-member's scalar size is handled on load/store.
            return

        if op == "load_member":
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            base_ty = self._var_types.get(base, "")
            if isinstance(base, str) and base.startswith("%t") and isinstance(base_ty, str) and (base_ty.strip().endswith("*") or base_ty.strip() == "ptr"):
                self._load_operand(base, "%rax")
            else:
                self._addr_of_symbol(base, "%rax")
            off = self._resolve_member_offset(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            # Bit-field read: shift + mask
            bf = self._resolve_bitfield(base, member)
            if bf is not None:
                bit_off, bit_w = bf
                self._emit("  movl (%rax), %eax")
                if bit_off > 0:
                    self._emit(f"  shrl ${bit_off}, %eax")
                mask = (1 << bit_w) - 1
                self._emit(f"  andl ${mask}, %eax")
                self._emit("  movslq %eax, %rax")
                self._store_result(ins.result, "%rax")
                return
            _, sz = self._resolve_member(base, member)
            if sz == 1:
                mem_ty = self._resolve_member_type(base, member)
                if isinstance(mem_ty, str) and "unsigned" in mem_ty:
                    self._emit("  movb (%rax), %al")
                    self._emit("  movzbq %al, %rax")
                else:
                    self._emit("  movb (%rax), %al")
                    self._emit("  movsbq %al, %rax")
            elif sz == 2:
                self._emit("  movw (%rax), %ax")
                self._emit("  movswq %ax, %rax")
            elif sz == 4:
                self._emit("  movl (%rax), %eax")
                self._emit("  movl %eax, %eax")
            else:
                self._emit("  movq (%rax), %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "addr_of_member_ptr":
            # result = &operand1->member
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            # Load pointer value into %rax then add member offset.
            self._load_operand(base, "%rax")
            off = self._resolve_member_offset(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "load_member_ptr":
            # result = operand1->member
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            # If IR carries struct type metadata from a cast, seed _var_types
            # so _resolve_member_offset can find the layout.
            if isinstance(ins.meta, dict) and "struct_type" in ins.meta:
                self._var_types[base] = f"{ins.meta['struct_type']}*"
            # Load pointer value into %rax then add member offset, then load value.
            self._load_operand(base, "%rax")
            off = self._resolve_member_offset(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            # Load the member value based on its size.
            _, sz = self._resolve_member(base, member)
            if sz == 1:
                mem_ty = self._resolve_member_type(base, member)
                if isinstance(mem_ty, str) and "unsigned" in mem_ty:
                    self._emit("  movb (%rax), %al")
                    self._emit("  movzbq %al, %rax")
                else:
                    self._emit("  movb (%rax), %al")
                    self._emit("  movsbq %al, %rax")
            elif sz == 2:
                self._emit("  movw (%rax), %ax")
                self._emit("  movswq %ax, %rax")
            elif sz == 4:
                self._emit("  movl (%rax), %eax")
                self._emit("  movl %eax, %eax")  # zero-extend to 64-bit
            else:
                self._emit("  movq (%rax), %rax")
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

        if op == "sext8":
            # Sign-extend low 8 bits to 64 bits.
            self._load_operand(ins.operand1, "%rax")
            self._emit("  movsbl %al, %eax")
            self._emit("  movslq %eax, %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "sext16":
            # Sign-extend low 16 bits to 64 bits.
            self._load_operand(ins.operand1, "%rax")
            self._emit("  movswl %ax, %eax")
            self._emit("  movslq %eax, %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "binop":
            self._load_operand(ins.operand1, "%rax")
            self._load_operand(ins.operand2, "%rcx")
            bop = ins.label

            # Pointer arithmetic scaling (best-effort): if either operand is a
            # pointer temp with an explicit step size, scale the integer operand.
            # This is used for multi-dimensional array decay where (p + 1)
            # should advance by sizeof(row).
            try:
                if bop in {"+", "-"}:
                    # 1) Temp-based overrides
                    s1 = self._ptr_step_bytes.get(str(ins.operand1 or ""))
                    s2 = self._ptr_step_bytes.get(str(ins.operand2 or ""))
                    # 2) Symbol-based overrides (e.g. local variable holding a
                    # decayed pointer value): use its declared type if it is
                    # pointer-typed.
                    if not s1 and isinstance(ins.operand1, str) and ("*" in self._var_types.get(ins.operand1, "")):
                        s1 = self._ptr_step_bytes.get(str(ins.operand1))
                    if not s2 and isinstance(ins.operand2, str) and ("*" in self._var_types.get(ins.operand2, "")):
                        s2 = self._ptr_step_bytes.get(str(ins.operand2))

                    if s1 and not s2:
                        step = int(s1)
                        if step != 1:
                            self._emit(f"  imulq ${step}, %rcx")
                    elif s2 and not s1 and bop == "+":
                        step = int(s2)
                        if step != 1:
                            self._emit(f"  imulq ${step}, %rax")
            except Exception:
                pass

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
                    # 32-bit unsigned arithmetic wraps modulo 2^32; ensure the
                    # computed value in %rax is zero-extended for subsequent 64-bit uses.
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  addq %rcx, %rax")
            elif bop == "-":
                if u32_arith:
                    self._emit("  subl %ecx, %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  subq %rcx, %rax")
            elif bop == "*":
                if u32_arith:
                    self._emit("  imull %ecx, %eax")
                    self._emit("  movl %eax, %eax")
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
                # Compare width matters: `unsigned int` values must be compared
                # in 32-bit to avoid treating zero-extended UINT32 as signed 64-bit.
                # Prefer 32-bit compare if either operand is known to be unsigned int.
                unsigned = bop.startswith("u")
                lty = self._var_types.get(ins.operand1 or "", "") if hasattr(self, "_var_types") else ""
                rty = self._var_types.get(ins.operand2 or "", "") if hasattr(self, "_var_types") else ""
                lty_n = lty.strip().lower() if isinstance(lty, str) else ""
                rty_n = rty.strip().lower() if isinstance(rty, str) else ""

                u32_cmp = (lty_n == "unsigned int") or (rty_n == "unsigned int")

                if u32_cmp:
                    # Use 32-bit registers for compare.
                    self._emit("  cmpl %ecx, %eax")
                else:
                    self._emit("  cmpq %rcx, %rax")

                # Signedness is decided in IR.
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
                if u32_arith:
                    self._emit("  andl %ecx, %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  andq %rcx, %rax")
            elif bop == "|":
                if u32_arith:
                    self._emit("  orl %ecx, %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  orq %rcx, %rax")
            elif bop == "^":
                if u32_arith:
                    self._emit("  xorl %ecx, %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  xorq %rcx, %rax")
            elif bop == "<<":
                self._emit("  movb %cl, %cl")
                if u32_arith:
                    self._emit("  shll %cl, %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  shlq %cl, %rax")
            elif bop == ">>":
                self._emit("  movb %cl, %cl")
                # Best-effort: if the left operand is declared unsigned, use logical shift.
                # Otherwise use arithmetic shift.
                lty = self._var_types.get(ins.operand1, "")
                if not lty and isinstance(ins.operand1, str) and ins.operand1.startswith("@") and self._sema_ctx is not None:
                    lty = getattr(self._sema_ctx, "global_types", {}).get(ins.operand1[1:], "")
                unsigned_left = isinstance(lty, str) and lty.strip().startswith("unsigned ")
                if u32_arith:
                    # For unsigned 32-bit, prefer logical shift; otherwise arithmetic.
                    if unsigned_left:
                        self._emit("  shrl %cl, %eax")
                    else:
                        self._emit("  sarl %cl, %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    if unsigned_left:
                        self._emit("  shrq %cl, %rax")
                    else:
                        self._emit("  sarq %cl, %rax")
            else:
                # unsupported operator
                pass

            self._store_result(ins.result, "%rax")
            return

        if op == "call":
            # Builtins: handle varargs setup/teardown without emitting external calls.
            # System headers expand va_start/va_end into these builtins.
            target0 = (ins.operand1 or "")
            if target0.startswith("@"):
                target0 = target0[1:]
            if target0 == "__builtin_va_end":
                # SysV: va_end is a no-op.
                self._store_result(ins.result, "$0")
                return

            if target0 == "__builtin_va_arg_int":
                # SysV AMD64 va_arg for GP (int/long/pointer) types.
                # Layout of __va_list_tag:
                #   +0: u32 gp_offset
                #   +4: u32 fp_offset
                #   +8: void* overflow_arg_area
                #  +16: void* reg_save_area
                ap = (ins.args or [None])[0]
                # ap is a pointer to the __va_list_tag (or the tag itself).
                self._addr_of_symbol(ap or "", "%rax")
                self._emit("  movq (%rax), %r11")  # r11 = &tag
                seq = getattr(self, "_va_label_seq", 0)
                self._va_label_seq = seq + 1
                lbl_stack = f".Lva_stack_{seq}"
                lbl_done = f".Lva_done_{seq}"
                # Check gp_offset < 48
                self._emit("  movl (%r11), %ecx")       # ecx = gp_offset
                self._emit("  cmpl $48, %ecx")
                self._emit(f"  jge {lbl_stack}")
                # Fetch from reg_save_area + gp_offset
                self._emit("  movq 16(%r11), %r10")      # r10 = reg_save_area
                self._emit("  movslq %ecx, %rcx")
                self._emit("  movq (%r10,%rcx), %rax")   # result
                # Advance gp_offset += 8
                self._emit("  addl $8, (%r11)")
                self._emit(f"  jmp {lbl_done}")
                # Fetch from overflow_arg_area
                self._emit(f"{lbl_stack}:")
                self._emit("  movq 8(%r11), %r10")       # r10 = overflow_arg_area
                self._emit("  movq (%r10), %rax")         # result
                self._emit("  addq $8, %r10")
                self._emit("  movq %r10, 8(%r11)")        # advance overflow_arg_area
                self._emit(f"{lbl_done}:")
                self._store_result(ins.result, "%rax")
                return

            if target0 == "__builtin_va_start":
                # SysV AMD64 minimal: initialize the 24-byte __va_list_tag so
                # passing it to libc (vsnprintf) works for GP args.
                # Layout (glibc):
                #   u32 gp_offset; u32 fp_offset; void* overflow; void* regsave;
                #
                # IMPORTANT: `va_list` on SysV is an array-of-1 struct. In C,
                # the macro expansion passes a `va_list` lvalue, so the builtin
                # receives a pointer to the first element (i.e. `&ap[0]`).
                #
                # If the frontend models `va_list` as the real array type, the
                # operand will be a stack slot containing the tag itself.
                # If the frontend models it as `void*` (via system-cpp defines),
                # the operand will be a pointer-sized slot that holds the tag
                # address, and we must load that pointer.
                ap = (ins.args or [None, None])[0]

                # We store a *tag pointer* into the user-visible `ap` local.
                # Our frame reserves a dedicated tag slot at rbp-_varargs_tag_base.
                self._addr_of_symbol(ap or "", "%rax")  # rax = &ap_slot
                tag_base = int(getattr(self, "_varargs_tag_base", 0) or 0)
                if not tag_base:
                    # Fallback: use the current frame bottom.
                    tag_base = int(getattr(self, "_stack_size", 0) or 0)
                self._emit(f"  leaq -{tag_base}(%rbp), %r12")
                self._emit("  movq %r12, (%rax)")
                tag_reg = "%r12"

                # gp_offset: offset of the first *variable* argument within
                # the GP save area. On SysV AMD64, the fixed args of the
                # variadic function may already occupy some registers.
                #
                # The System V ABI uses a 6-slot GP area:
                #   rdi,rsi,rdx,rcx,r8,r9
                # For our supported subset, compute gp_offset from the number
                # of fixed params, but note that `va_start(ap, last_named)`
                # should start *after* the last named argument.
                named_gp = int(getattr(self, "_varargs_named_gpr_count", 0) or 0)
                # SysV AMD64: gp_offset is the byte offset *within the GP save area*
                # of the next argument to be fetched. It should point to the first
                # *variadic* argument slot, i.e. right after the last named argument.
                #
                # Example: wrap(out, n, fmt, ...) has 3 named GP args:
                #   out -> rdi (slot 0)
                #   n   -> rsi (slot 1)
                #   fmt -> rdx (slot 2)
                # so the first vararg is in rcx (slot 3) => gp_offset = 3*8.
                gp_off = min(self._VARARGS_GP_SAVE_AREA_SIZE, named_gp * 8)
                self._emit(f"  movl ${gp_off}, ({tag_reg})")
                # fp_offset: byte offset within reg_save_area where FP regs start.
                # SysV AMD64: FP area starts after 48 bytes of GP slots.
                self._emit(f"  movl ${self._VARARGS_GP_SAVE_AREA_SIZE}, 4({tag_reg})")

                # overflow_arg_area: point to first stack vararg.
                # Best-effort default: just past the return address.
                # (Only used when gp_offset exceeds 48.)
                # SysV frame: 0(%rbp)=old rbp, 8(%rbp)=retaddr, so +16 is the
                # first stack argument slot.
                self._emit(f"  leaq {self._VARARGS_FIRST_STACK_ARG_OFF}(%rbp), %r10")
                self._emit(f"  movq %r10, 8({tag_reg})")

                # Keep reg_save_area's GP slots consistent with the ABI.
                # We save incoming arg regs in the prologue; refresh the
                # vararg-relevant slots (rcx/r8/r9) in case later codegen
                # clobbered them before va_start runs.
                base = int(getattr(self, "_varargs_reg_save_base", 0) or 0)
                if base:
                    # With ascending layout: rdi at -(base+40), rsi at -(base+32), ...
                    # rcx at -(base+16), r8 at -(base+8), r9 at -(base+0)
                    self._emit(f"  movq %rcx, -{base + 16}(%rbp)")
                    self._emit(f"  movq %r8,  -{base + 8}(%rbp)")
                    self._emit(f"  movq %r9,  -{base + 0}(%rbp)")

                # reg_save_area: points to rdi slot (lowest address).
                base = int(getattr(self, "_varargs_reg_save_base", 0) or 0)
                if base:
                    self._emit(f"  leaq -{base + 40}(%rbp), %r11")
                else:
                    # Fallback (should not happen for a true variadic function)
                    base2 = int(getattr(self, "_locals_base", 0))
                    self._emit(f"  leaq -{base2 + 48 + 128}(%rbp), %r11")
                self._emit(f"  movq %r11, 16({tag_reg})")



                self._store_result(ins.result, "$0")
                return

            # Ensure the stack is 16-byte aligned at the call instruction.
            # Our codegen sometimes grows the stack dynamically (e.g. spilling temps)
            # or does ad-hoc pushes; libc functions like printf assume proper alignment.
            # If currently misaligned, temporarily adjust by 8 and undo after call.
            pre_call_pad = False
            if getattr(self, "_call_stack_adjust", 0) % 16 != 0:
                # SysV AMD64 ABI: %rsp must be 16-byte aligned at each `call`.
                self._emit("  subq $8, %rsp")
                self._call_stack_adjust = getattr(self, "_call_stack_adjust", 0) + 8
                pre_call_pad = True

            # operand1 is function name or @name
            # args are operand strings
            arg_regs = ["%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"]

            xmm_regs = ["%xmm0", "%xmm1", "%xmm2", "%xmm3", "%xmm4", "%xmm5", "%xmm6", "%xmm7"]
            gp_idx = 0
            xmm_idx = 0

            # SysV AMD64: args beyond r9 go on the stack (right-to-left).
            stack_args = list(ins.args or [])[len(arg_regs):]
            stack_pad = 0

            if stack_args:
                for a in reversed(stack_args):
                    self._load_operand(a, "%rax")
                    self._emit("  pushq %rax")
                    stack_pad += 8
                self._call_stack_adjust = getattr(self, "_call_stack_adjust", 0) + stack_pad

            # --- Two-pass argument setup for struct-aware ABI ---
            # Pass 1: Pre-allocate stack copies for large (MEMORY class) structs
            #         and record the stack pointer for each.  This must happen
            #         before we start loading argument registers because the
            #         copy may clobber scratch registers.
            # Pass 2: Load all arguments into their target registers.

            # SysV ABI: if the callee returns a MEMORY-class struct, the caller
            # must allocate space and pass a hidden pointer via %rdi as the
            # implicit first argument.
            _ret_hidden_ptr_slot = 0  # spill offset for the hidden return pointer
            ret_ty = str(ins.operand2 or "")
            _call_ret_ty_s = ret_ty.replace("function ", "").strip() if ret_ty.startswith("function ") else ""
            _call_ret_is_memory = False
            if _call_ret_ty_s.startswith("struct ") or _call_ret_ty_s.startswith("union "):
                _call_ret_sz = self._type_size_bytes(_call_ret_ty_s)
                _call_ret_layout = getattr(self._sema_ctx, "layouts", {}).get(_call_ret_ty_s) if self._sema_ctx else None
                _call_ret_cls = classify_struct(_call_ret_ty_s, _call_ret_layout) if _call_ret_layout else [EightbyteClass.INTEGER]
                _call_ret_pm = get_struct_pass_mode(_call_ret_cls)
                if _call_ret_pm == "hidden_ptr":
                    _call_ret_is_memory = True
                    # Allocate space on the stack for the return value.
                    alloc_sz = ((_call_ret_sz + 15) // 16) * 16  # 16-byte aligned
                    alloc_sz = max(alloc_sz, 16)
                    self._emit(f"  subq ${alloc_sz}, %rsp")
                    stack_pad += alloc_sz
                    self._call_stack_adjust = getattr(self, "_call_stack_adjust", 0) + alloc_sz
                    # Save the pointer in a temp slot for later use.
                    tmp = self._new_spill_name()
                    _ret_hidden_ptr_slot = self._ensure_local(tmp)
                    self._emit(f"  movq %rsp, %rax")
                    self._emit(f"  movq %rax, -{_ret_hidden_ptr_slot}(%rbp)")
                    # Hidden return pointer consumes %rdi (first GP register).
                    gp_idx = 1

            # Build an argument descriptor list.
            _arg_descs = []  # list of (arg, a_ty, kind, extra)
            #   kind: 'float', 'long_double', 'struct_reg', 'struct_hidden', 'struct_stack', 'gp'
            #   extra: for struct_hidden -> temp slot offset holding the pointer
            _pre_gp = gp_idx
            _pre_xmm = 0
            for idx, a in enumerate(ins.args or []):
                a_ty = self._var_types.get(a, "") if isinstance(a, str) else ""
                if isinstance(a_ty, str) and a_ty.strip() == "long double":
                    # SysV ABI: long double is MEMORY class, passed on the stack
                    _arg_descs.append((a, a_ty, "long_double", None))
                elif isinstance(a_ty, str) and a_ty in ("float", "double"):
                    _arg_descs.append((a, a_ty, "float", None))
                    _pre_xmm += 1
                elif isinstance(a_ty, str) and (a_ty.strip().startswith("struct ") or a_ty.strip().startswith("union ")) and "*" not in a_ty:
                    sty = a_ty.strip()
                    sz = self._type_size_bytes(sty)
                    layout = getattr(self._sema_ctx, "layouts", {}).get(sty) if self._sema_ctx else None
                    classification = classify_struct(sty, layout) if layout else [EightbyteClass.INTEGER]
                    pass_mode = get_struct_pass_mode(classification)
                    if pass_mode == "hidden_ptr":
                        _arg_descs.append((a, a_ty, "struct_hidden", {"sz": sz, "classification": classification}))
                        _pre_gp += 1  # hidden pointer consumes one GP reg
                    elif pass_mode == "registers":
                        gp_needed = sum(1 for c in classification if c == EightbyteClass.INTEGER)
                        sse_needed = sum(1 for c in classification if c == EightbyteClass.SSE)
                        if _pre_gp + gp_needed <= len(arg_regs) and _pre_xmm + sse_needed <= len(xmm_regs):
                            _arg_descs.append((a, a_ty, "struct_reg", {"sz": sz, "classification": classification}))
                            _pre_gp += gp_needed
                            _pre_xmm += sse_needed
                        else:
                            _arg_descs.append((a, a_ty, "struct_stack", {"sz": sz, "classification": classification}))
                    else:
                        _arg_descs.append((a, a_ty, "struct_stack", {"sz": sz, "classification": classification}))
                else:
                    _arg_descs.append((a, a_ty, "gp", None))
                    _pre_gp += 1

            # Pass 1: allocate stack copies for hidden_ptr structs.
            # We store the resulting pointer in a temp spill slot so that
            # Pass 2 can load it into the correct GP register without
            # clobbering other argument registers.
            _hidden_ptr_slots = {}  # arg index -> spill offset
            for desc_idx, (a, a_ty, kind, extra) in enumerate(_arg_descs):
                if kind == "struct_hidden":
                    sz = extra["sz"]
                    off = self._ensure_local(a)
                    alloc_sz = ((sz + 7) // 8) * 8
                    self._emit(f"  subq ${alloc_sz}, %rsp")
                    stack_pad += alloc_sz
                    self._call_stack_adjust = getattr(self, "_call_stack_adjust", 0) + alloc_sz
                    # Copy struct data to the stack copy using movq loop
                    # (avoids clobbering rdi/rsi/rcx which are arg registers).
                    chunks = (sz + 7) // 8
                    for ci in range(chunks):
                        self._emit(f"  movq -{off - ci * 8}(%rbp), %rax")
                        self._emit(f"  movq %rax, {ci * 8}(%rsp)")
                    # Save the pointer to the copy in a temp slot.
                    tmp = self._new_spill_name()
                    tmp_off = self._ensure_local(tmp)
                    self._emit(f"  movq %rsp, %rax")
                    self._emit(f"  movq %rax, -{tmp_off}(%rbp)")
                    _hidden_ptr_slots[desc_idx] = tmp_off

            # Also push struct_stack args and long_double args (register-exhausted structs) right-to-left.
            for desc_idx in reversed(range(len(_arg_descs))):
                a, a_ty, kind, extra = _arg_descs[desc_idx]
                if kind == "long_double":
                    # SysV ABI: long double passed on stack (16 bytes)
                    off = self._ensure_local(a, size=16)
                    # Push high 8 bytes first, then low 8 bytes (right-to-left)
                    self._emit(f"  pushq -{off - 8}(%rbp)")
                    self._emit(f"  pushq -{off}(%rbp)")
                    stack_pad += 16
                    self._call_stack_adjust = getattr(self, "_call_stack_adjust", 0) + 16
                elif kind == "struct_stack":
                    sz = extra["sz"]
                    off = self._ensure_local(a)
                    chunks = (sz + 7) // 8
                    for ci in reversed(range(chunks)):
                        self._emit(f"  pushq -{off - ci * 8}(%rbp)")
                        stack_pad += 8
                    self._call_stack_adjust = getattr(self, "_call_stack_adjust", 0) + chunks * 8

            # Pass 2: load arguments into registers.
            # If there's a hidden return pointer, load it into %rdi first.
            if _call_ret_is_memory and _ret_hidden_ptr_slot:
                self._emit(f"  movq -{_ret_hidden_ptr_slot}(%rbp), %rdi")
            for desc_idx, (a, a_ty, kind, extra) in enumerate(_arg_descs):
                if kind == "float":
                    if xmm_idx < len(xmm_regs):
                        s = "s" if a_ty == "float" else "d"
                        off = self._ensure_local(a)
                        self._emit(f"  movs{s} -{off}(%rbp), {xmm_regs[xmm_idx]}")
                        xmm_idx += 1
                elif kind == "struct_reg":
                    classification = extra["classification"]
                    off = self._ensure_local(a)
                    for ci, cls in enumerate(classification):
                        if cls == EightbyteClass.SSE:
                            self._emit(f"  movq -{off - ci * 8}(%rbp), {xmm_regs[xmm_idx]}")
                            xmm_idx += 1
                        else:
                            self._emit(f"  movq -{off - ci * 8}(%rbp), {arg_regs[gp_idx]}")
                            gp_idx += 1
                elif kind == "struct_hidden":
                    # Load the saved pointer from the temp slot.
                    tmp_off = _hidden_ptr_slots[desc_idx]
                    if gp_idx < len(arg_regs):
                        self._emit(f"  movq -{tmp_off}(%rbp), {arg_regs[gp_idx]}")
                        gp_idx += 1
                elif kind == "struct_stack":
                    pass  # already pushed in pass 1
                elif kind == "long_double":
                    pass  # already pushed on stack in pass 1
                elif kind == "gp":
                    if gp_idx < len(arg_regs):
                        self._load_operand(a, "%rax")
                        self._emit(f"  movq %rax, {arg_regs[gp_idx]}")
                        gp_idx += 1

            # ABI fix: SysV `va_list` is an array-of-1 tag; when passed as an
            # argument it decays to a pointer to that tag.
            target_name = (ins.operand1 or "")
            if target_name.startswith("@"):  # symbol
                target_name = target_name[1:]

            # SysV AMD64 ABI: for variadic calls, %al must contain the number
            # of vector registers used to pass arguments. We don't pass any
            # vector args yet, so clear %eax.
            # This is required for calls like printf("%d\n", 42).
            if isinstance(ins.operand2, str) and "..." in ins.operand2:
                if xmm_idx > 0:
                    self._emit(f"  movl ${xmm_idx}, %eax")
                else:
                    self._emit("  xorl %eax, %eax")

            # IMPORTANT: for glibc v* functions that take a `va_list`, the caller
            # should not clear %al unless the function is variadic. These v*
            # entrypoints are not variadic.

            # Final fixup: if calling a libc v* function and the 4th argument is
            # a local va_list variable, ensure we pass the tag pointer it holds
            # (not the address of the local slot).
            if target_name in {"vsnprintf", "vprintf", "vfprintf", "vsprintf", "vasprintf", "vdprintf"}:
                if ins.args and len(ins.args) >= 4:
                    a3 = ins.args[3]
                    if isinstance(a3, str) and a3.startswith("@"):
                        # 4th arg is %rcx
                        self._addr_of_symbol(a3, "%rax")
                        self._emit("  movq %rax, %rcx")
                        self._emit("  movq (%rcx), %rcx")

            target = ins.operand1 or ""
            if target.startswith("@"):  # symbol
                # If it names a function symbol, do a direct call. This must
                # work across translation units (extern prototypes).
                sym = target[1:]
                # If it's a local variable/temp, it's not a function symbol.
                if self._is_local(target):
                    # If semantics says this name is a function (e.g. an
                    # extern prototype declared inside a function), emit a
                    # direct call instead of indirect through an uninitialized
                    # local slot.
                    gty = getattr(self._sema_ctx, "global_types", {}).get(sym) if self._sema_ctx is not None else None
                    if isinstance(gty, str) and gty.strip().startswith("function"):
                        # Keep SysV varargs ABI happy for calls the IR marks
                        # as variadic (operand2 contains "...").
                        if isinstance(ins.operand2, str) and "..." in ins.operand2:
                            # SysV x86-64: for variadic calls, %al must contain
                            # the number of XMM registers used to pass float
                            # args. We don't pass floats yet, so set 0.
                            self._emit("  xorl %eax, %eax")
                        self._emit(f"  call {sym}")
                        self._store_result(ins.result, "%rax")
                        return
                    self._load_operand(target, "%rax")
                    self._emit("  call *%rax")
                    self._store_result(ins.result, "%rax")
                    return
                # Heuristic: if it's defined in this TU, it's definitely a function.
                # Otherwise, if semantics says it's externally linked, also treat as function.
                is_func = sym in getattr(self, "_functions", set())
                if not is_func and self._sema_ctx is not None:
                    # If semantics recorded it as a function, prefer a direct call.
                    gty = getattr(self._sema_ctx, "global_types", {}).get(sym)
                    if isinstance(gty, str) and gty.strip().startswith("function"):
                        is_func = True
                    else:
                        # If it's not a known global variable, treat as a function symbol.
                        # This allows extern prototypes across translation units.
                        is_func = sym not in getattr(self._sema_ctx, "global_linkage", {})
                # If we don't have semantic info, still treat unknown @symbols
                # as functions by default. This avoids generating
                # `movslq foo(%rip), %rax; call *%rax` for extern functions.
                if not is_func and self._sema_ctx is None:
                    is_func = True
                if is_func:
                    self._emit(f"  call {sym}")
                else:
                    # Otherwise treat it as a function pointer variable.
                    self._load_operand(target, "%rax")
                    self._emit("  call *%rax")
            else:
                # Indirect call via function pointer stored in a local/temp.
                if not target.startswith("%t") and not target.startswith("@"):
                    # Parser/IR may pass a bare identifier for local variables.
                    target = f"@{target}"
                self._load_operand(target, "%rax")
                self._emit("  call *%rax")

            if pre_call_pad:
                self._emit("  addq $8, %rsp")
                self._call_stack_adjust = max(0, getattr(self, "_call_stack_adjust", 0) - 8)

            if stack_pad:
                self._emit(f"  addq ${stack_pad}, %rsp")
                self._call_stack_adjust = max(0, getattr(self, "_call_stack_adjust", 0) - stack_pad)
            # long double return: SysV ABI returns via x87 st(0)
            ret_ty = str(ins.operand2 or "")
            _ret_is_ld = False
            if "long double" in ret_ty and "function" in ret_ty:
                _ret_is_ld = True
            elif ins.result and isinstance(self._var_types.get(ins.result, ""), str) and self._var_types.get(ins.result, "").strip() == "long double":
                _ret_is_ld = True
            if _ret_is_ld:
                if ins.result:
                    off_r = self._ensure_local(ins.result, size=16)
                    self._emit(f"  fstpt -{off_r}(%rbp)")
                    self._var_types[ins.result] = "long double"
                else:
                    # Pop x87 stack if no result needed
                    self._emit("  fstp %st(0)")
            # Float return: result in xmm0
            elif "float" in ret_ty and "function" in ret_ty:
                fp = "float" if ret_ty.endswith("float") else "double"
                s = "s" if fp == "float" else "d"
                if ins.result:
                    off_r = self._ensure_local(ins.result)
                    self._emit(f"  movs{s} %xmm0, -{off_r}(%rbp)")
                    self._var_types[ins.result] = fp
            else:
                # Struct/union return: use StructClassifier to determine registers.
                ret_ty_s = ret_ty.replace("function ", "").strip() if ret_ty.startswith("function ") else ""
                if ret_ty_s.startswith("struct ") or ret_ty_s.startswith("union "):
                    sz = self._type_size_bytes(ret_ty_s)
                    layout = getattr(self._sema_ctx, "layouts", {}).get(ret_ty_s) if self._sema_ctx else None
                    ret_classification = classify_struct(ret_ty_s, layout) if layout else [EightbyteClass.INTEGER]
                    ret_pass_mode = get_struct_pass_mode(ret_classification)

                    if ret_pass_mode == "hidden_ptr":
                        # MEMORY class: the hidden pointer was passed via rdi
                        # before the call.  The callee returns the pointer in
                        # rax.  Copy the data from the pointed-to area into
                        # the local result slot.
                        if ins.result:
                            alloc_sz = ((sz + 7) // 8) * 8
                            alloc_sz = max(alloc_sz, 8)
                            off_r = self._ensure_local(ins.result, size=alloc_sz)
                            # rax holds the pointer to the returned struct data.
                            self._emit(f"  movq %rax, %rsi")
                            self._emit(f"  leaq -{off_r}(%rbp), %rdi")
                            self._emit(f"  movq ${sz}, %rcx")
                            self._emit("  rep movsb")
                            self._var_types[ins.result] = ret_ty_s
                    else:
                        # Register return: extract from rax/rdx and/or xmm0/xmm1.
                        if ins.result:
                            alloc_sz = ((sz + 7) // 8) * 8
                            alloc_sz = max(alloc_sz, 8)
                            off_r = self._ensure_local(ins.result, size=alloc_sz)
                            ret_gp_regs = ["%rax", "%rdx"]
                            ret_xmm_regs = ["%xmm0", "%xmm1"]
                            gp_ri = 0
                            xmm_ri = 0
                            for ci, cls in enumerate(ret_classification):
                                if cls == EightbyteClass.SSE:
                                    self._emit(f"  movq {ret_xmm_regs[xmm_ri]}, -{off_r - ci * 8}(%rbp)")
                                    xmm_ri += 1
                                else:
                                    self._emit(f"  movq {ret_gp_regs[gp_ri]}, -{off_r - ci * 8}(%rbp)")
                                    gp_ri += 1
                            self._var_types[ins.result] = ret_ty_s
                        self._var_types[ins.result] = ret_ty_s
                else:
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
            step_override = None
            try:
                # Prefer instruction-scoped override (IR meta) when present.
                if isinstance(ins.meta, dict) and "ptr_step_bytes" in ins.meta:
                    step_override = int(ins.meta["ptr_step_bytes"])
                else:
                    step_override = self._ptr_step_bytes.get(str(base))
            except Exception:
                step_override = None
            if isinstance(base, str):
                base_ty = self._var_types.get(base)
                if base_ty is None and base.startswith("@"):
                    sym = base[1:]
                    base_ty = getattr(self._sema_ctx, "global_types", {}).get(sym) if self._sema_ctx is not None else None

            # If IR annotated the result temp with a scalar type (e.g. "char"),
            # prefer that as the element type for width decisions. This is
            # important for multi-dimensional array indexing where the base can
            # be a row-object temp.
            try:
                if ins.result:
                    rty = self._var_types.get(str(ins.result))
                    if isinstance(rty, str) and rty and ("*" not in rty) and not rty.strip().startswith("array("):
                        elem_sz = self._type_size_bytes(rty.strip())
            except Exception:
                pass

            # Prefer scalar element type hint from IR on the *result temp*.
            # This must override any base-derived element size (including row
            # objects in multi-dimensional arrays).
            try:
                if ins.result:
                    rty = self._var_types.get(str(ins.result))
                    if isinstance(rty, str) and rty.strip() and ("*" not in rty) and not rty.strip().startswith("array("):
                        elem_sz = self._type_size_bytes(rty.strip())
            except Exception:
                pass

            if isinstance(base_ty, str) and base_ty.strip().startswith("array("):
                # array(T,$N)
                inner = base_ty.strip()[len("array(") :]
                if inner.endswith(")"):
                    inner = inner[:-1]
                base_part = inner.split(",", 1)[0].strip()
                # Only compute elem_sz from base when IR didn't provide a more
                # specific scalar result type.
                if elem_sz == 4:
                    elem_sz = self._type_size_bytes(base_part)
            elif isinstance(base_ty, str) and "*" in base_ty:
                elem_sz = self._pointee_size_bytes(base_ty)
            elif isinstance(base_ty, str):
                # Global fixed-size arrays are currently tracked as just their
                # element type (e.g. "char"); use that to pick element size.
                # This is best-effort until we add explicit global array types.
                elem_sz = self._type_size_bytes(base_ty.strip())
            elif isinstance(base, str) and base.startswith("%t"):
                # For temps used as addresses, consult `_var_types` to infer pointee size.
                tyt = self._var_types.get(base)
                if isinstance(tyt, str) and "*" in tyt:
                    elem_sz = self._pointee_size_bytes(tyt)
                else:
                    # Fall back: if the base temp comes from an address-of array,
                    # its pointee is typically an int-sized element .
                    # Keep elem_sz as-is.
                    pass

            # A temp base is treated as a pointer/address value only when it is
            # pointer-typed (or explicitly tagged as ptr). Temps that represent
            # array objects (e.g. row objects in multi-dimensional indexing)
            # must be addressed, not loaded.
            is_ptr_temp = False
            if isinstance(base, str) and base.startswith("%t"):
                if isinstance(base_ty, str) and ("*" in base_ty or base_ty.strip() == "ptr"):
                    is_ptr_temp = True
            is_ptr_base = (isinstance(base_ty, str) and "*" in base_ty) or is_ptr_temp
            # compute address: base + idx*elem_sz
            # - if base is a pointer value, load the pointer value
            # - else treat it as an array object and take its address
            if is_ptr_base:
                self._load_operand(base, "%rax")
            else:
                # base is an array object or a raw address temp
                self._addr_of_symbol(base, "%rax")
            self._load_operand(idx, "%rcx")
            # Multi-dimensional arrays: when indexing a row-pointer, scale by
            # the row size (bytes), not by sizeof(element).
            if isinstance(step_override, int) and step_override > 0:
                self._emit(f"  imulq ${int(step_override)}, %rcx")
            elif elem_sz != 1:
                self._emit(f"  imulq ${elem_sz}, %rcx")
            self._emit("  addq %rcx, %rax")
            # load with width based on element size
            if elem_sz == 1:
                # char loads: choose sign/zero extension based on pointee type.
                unsigned_char = False
                if isinstance(base_ty, str) and "unsigned" in base_ty and "char" in base_ty:
                    unsigned_char = True
                if unsigned_char:
                    self._emit("  movzbl (%rax), %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  movsbl (%rax), %eax")
                    self._emit("  movslq %eax, %rax")
            elif elem_sz == 2:
                self._emit("  movswq (%rax), %rax")
            elif elem_sz == 4:
                self._emit("  movslq (%rax), %rax")
            else:
                self._emit("  movq (%rax), %rax")
            self._store_result(ins.result, "%rax")
            return

        if op == "load_member":
            # treat operand1 as addressable base (stack local), operand2 as member name.
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            # Compute base address.
            # - locals/globals: take address of the symbol
            # - temps holding addresses (e.g. from addr_index/addr_of_member): load pointer value
            # For load_member we want the *pointee* type when `base` is a pointer.
            base_ty = self._var_types.get(base, "")
            if isinstance(base_ty, str) and base_ty.strip().endswith("*"):
                base_ty = base_ty.strip()[:-1].strip()
            # For temps, decide whether it holds an address (pointer value) or a scalar.
            # - If we know it is pointer-typed ("...*") or tagged as "ptr", treat as pointer value.
            # - Otherwise it's a scalar temp stored in a stack slot; use its address as base.
            # IMPORTANT: for non-temp locals like "@s" (a struct object), ALWAYS take
            # the address of the object. Do not treat it as a pointer even if the type
            # string contains '*' somewhere (e.g. "struct X*" for pointer vars).
            if isinstance(base, str) and base.startswith("%t"):
                # Temps may hold either a pointer value or a scalar in a spill slot.
                if isinstance(base_ty, str) and (base_ty.strip().endswith("*") or base_ty == "ptr"):
                    self._load_operand(base, "%rax")
                else:
                    self._addr_of_symbol(base, "%rax")
            else:
                # Non-temp: treat as pointer value only if the variable is pointer-typed.
                if isinstance(base_ty, str) and base_ty.strip().endswith("*"):
                    self._load_operand(base, "%rax")
                else:
                    self._addr_of_symbol(base, "%rax")
            off, sz = self._resolve_member(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")

            # If the member itself is a struct/union, `load_member` should yield
            # its address (so subsequent `.x` accesses don't interpret the first
            # bytes of the subobject as a pointer).
            mem_ty = self._resolve_member_type(base, member)
            # Fallback: for locals, semantic typing might not be available.
            # If IR recorded the member access result as a struct/union type,
            # treat it as an address.
            if mem_ty is None:
                try:
                    rty = self._var_types.get(ins.result or "")
                except Exception:
                    rty = None
                if isinstance(rty, str) and (rty.strip().startswith("struct ") or rty.strip().startswith("union ")):
                    mem_ty = rty.strip()
            if mem_ty is not None:
                mem_ty_s = str(mem_ty).strip()
                if mem_ty_s.startswith("struct ") or mem_ty_s.startswith("union "):
                    if ins.result and isinstance(ins.result, str) and ins.result.startswith("%t"):
                        self._var_types[ins.result] = f"{mem_ty_s}*"
                    self._store_result(ins.result, "%rax")
                    return

            # load based on member size
            if sz == 1:
                # Best-effort signedness for 1-byte members.
                # Default C89: plain `char` is implementation-defined. This
                # backend treats `char` as signed.
                mem_ty_s = str(mem_ty).strip().lower() if mem_ty is not None else ""
                is_unsigned = mem_ty_s.startswith("unsigned char")
                if is_unsigned:
                    self._emit("  movzbl (%rax), %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  movsbl (%rax), %eax")
                    self._emit("  movslq %eax, %rax")
            elif sz == 4:
                self._emit("  movl (%rax), %eax")
                self._emit("  movl %eax, %eax")
                # Keep as zero-extended 32-bit in %rax; signedness is handled
                # by downstream casts/ops.
            else:
                self._emit("  movq (%rax), %rax")
            # After loading the member value, %rax no longer holds an address.
            if ins.result and isinstance(ins.result, str) and ins.result.startswith("%t"):
                self._var_types[ins.result] = "long"
            self._store_result(ins.result, "%rax")
            return

        if op == "load_member_ptr":
            # operand1 holds pointer value; load it as address then add member offset
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            if isinstance(ins.meta, dict) and "struct_type" in ins.meta:
                self._var_types[base] = f"{ins.meta['struct_type']}*"
            self._load_operand(base, "%rax")
            off, sz = self._resolve_member(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            if sz == 1:
                mem_ty = None
                try:
                    mem_ty = self._resolve_member_type(base, member)
                except Exception:
                    mem_ty = None
                mem_ty_s = str(mem_ty).strip().lower() if mem_ty is not None else ""
                is_unsigned = mem_ty_s.startswith("unsigned char")
                if is_unsigned:
                    self._emit("  movzbl (%rax), %eax")
                    self._emit("  movl %eax, %eax")
                else:
                    self._emit("  movsbl (%rax), %eax")
                    self._emit("  movslq %eax, %rax")
            elif sz == 4:
                self._emit("  movl (%rax), %eax")
                self._emit("  movl %eax, %eax")
                # Keep as zero-extended 32-bit in %rax.
            else:
                self._emit("  movq (%rax), %rax")
            if ins.result and isinstance(ins.result, str) and ins.result.startswith("%t"):
                self._var_types[ins.result] = "long"
            self._store_result(ins.result, "%rax")
            return


        if op == "store_member":
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            val = ins.result
            base_ty = self._var_types.get(base, "")
            if isinstance(base, str) and base.startswith("%t"):
                self._load_operand(base, "%rax")
            elif isinstance(base_ty, str) and "*" in base_ty:
                self._load_operand(base, "%rax")
            else:
                self._addr_of_symbol(base, "%rax")
            off, sz = self._resolve_member(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            # Bit-field write: read-modify-write
            bf = self._resolve_bitfield(base, member)
            if bf is not None:
                bit_off, bit_w = bf
                mask = (1 << bit_w) - 1
                self._emit("  movq %rax, %rdx")  # save address
                self._load_operand(val, "%rcx")
                self._emit(f"  andl ${mask}, %ecx")  # mask new value
                if bit_off > 0:
                    self._emit(f"  shll ${bit_off}, %ecx")  # shift to position
                clear_mask = ~(mask << bit_off) & 0xFFFFFFFF
                self._emit("  movl (%rdx), %eax")  # load current word
                self._emit(f"  andl ${clear_mask}, %eax")  # clear bits
                self._emit("  orl %ecx, %eax")  # set new bits
                self._emit("  movl %eax, (%rdx)")  # store back
                return
            self._load_operand(val, "%rcx")
            if sz == 1:
                self._emit("  movb %cl, (%rax)")
            elif sz == 4:
                self._emit("  movl %ecx, (%rax)")
            else:
                self._emit("  movq %rcx, (%rax)")
            return


        if op == "store_member_ptr":
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            val = ins.result
            if isinstance(ins.meta, dict) and "struct_type" in ins.meta:
                self._var_types[base] = f"{ins.meta['struct_type']}*"
            self._load_operand(base, "%rax")
            off, sz = self._resolve_member(base, member)
            if off:
                self._emit(f"  addq ${off}, %rax")
            self._load_operand(val, "%rcx")
            if sz == 1:
                self._emit("  movb %cl, (%rax)")
            elif sz == 4:
                self._emit("  movl %ecx, (%rax)")
            else:
                self._emit("  movq %rcx, (%rax)")
            return

        if op == "store_member_ptr":
            base = ins.operand1 or ""
            member = ins.operand2 or ""
            val = ins.result
            if isinstance(ins.meta, dict) and "struct_type" in ins.meta:
                self._var_types[base] = f"{ins.meta['struct_type']}*"
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
            # Check if returning a float value
            src = ins.operand1 or ""
            src_ty = self._var_types.get(src, "") if isinstance(src, str) else ""
            rty = getattr(self, "_fn_ret_ty", "") or ""

            # long double return: SysV ABI returns via x87 st(0)
            if isinstance(src_ty, str) and src_ty.strip() == "long double":
                off = self._ensure_local(src, size=16)
                self._emit(f"  fldt -{off}(%rbp)")
                self._emit("  leave")
                self._emit("  ret")
                return
            if isinstance(rty, str) and rty.strip() == "long double":
                off = self._ensure_local(src, size=16)
                self._emit(f"  fldt -{off}(%rbp)")
                self._emit("  leave")
                self._emit("  ret")
                return

            if isinstance(src_ty, str) and src_ty in ("float", "double"):
                s = "s" if src_ty == "float" else "d"
                off = self._ensure_local(src)
                self._emit(f"  movs{s} -{off}(%rbp), %xmm0")
                self._emit("  leave")
                self._emit("  ret")
                return
            if isinstance(rty, str) and rty.strip() in ("float", "double"):
                s = "s" if rty.strip() == "float" else "d"
                off = self._ensure_local(src)
                self._emit(f"  movs{s} -{off}(%rbp), %xmm0")
                self._emit("  leave")
                self._emit("  ret")
                return

            # Struct/union by-value return: use StructClassifier to decide registers.
            if isinstance(src_ty, str) and (src_ty.strip().startswith("struct ") or src_ty.strip().startswith("union ")):
                sty = src_ty.strip()
                sz = self._type_size_bytes(sty)
                off = self._ensure_local(src)
                layout = getattr(self._sema_ctx, "layouts", {}).get(sty) if self._sema_ctx else None
                classification = classify_struct(sty, layout) if layout else [EightbyteClass.INTEGER]
                pass_mode = get_struct_pass_mode(classification)

                if pass_mode == "hidden_ptr":
                    # MEMORY class: copy struct data to the hidden pointer
                    # location (saved in prologue at _hidden_ret_ptr_off).
                    hidden_off = getattr(self, "_hidden_ret_ptr_off", 0)
                    if hidden_off:
                        # Load hidden pointer into rdi, source into rsi, copy.
                        self._emit(f"  movq -{hidden_off}(%rbp), %rdi")
                        self._emit(f"  leaq -{off}(%rbp), %rsi")
                        self._emit(f"  movq ${sz}, %rcx")
                        self._emit("  rep movsb")
                        # Return the hidden pointer in rax.
                        self._emit(f"  movq -{hidden_off}(%rbp), %rax")
                    self._emit("  leave")
                    self._emit("  ret")
                    return

                # Register return: use classification to pick rax/rdx vs xmm0/xmm1.
                ret_gp_regs = ["%rax", "%rdx"]
                ret_xmm_regs = ["%xmm0", "%xmm1"]
                gp_i = 0
                xmm_i = 0
                for ci, cls in enumerate(classification):
                    if cls == EightbyteClass.SSE:
                        self._emit(f"  movq -{off - ci * 8}(%rbp), {ret_xmm_regs[xmm_i]}")
                        xmm_i += 1
                    else:
                        self._emit(f"  movq -{off - ci * 8}(%rbp), {ret_gp_regs[gp_i]}")
                        gp_i += 1
                self._emit("  leave")
                self._emit("  ret")
                return

            self._load_operand(src, "%rax")

            if not rty:
                try:
                    rty = (self._var_types.get(ins.operand1 or "", "") if hasattr(self, "_var_types") else "")
                except Exception:
                    rty = ""

            rty_n = rty.strip().lower() if isinstance(rty, str) else ""
            # Never apply narrow-type extension for pointer return types.
            if "*" not in rty_n:
                if rty_n in {"short", "signed short"}:
                    self._emit("  movswl %ax, %eax")
                    self._emit("  movslq %eax, %rax")
                elif rty_n == "unsigned short":
                    self._emit("  movzwl %ax, %eax")
                    self._emit("  movl %eax, %eax")
                elif rty_n in {"char", "signed char"}:
                    self._emit("  movsbl %al, %eax")
                    self._emit("  movslq %eax, %rax")
                elif rty_n == "unsigned char":
                    self._emit("  movzbl %al, %eax")
                    self._emit("  movl %eax, %eax")
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

    # Operand helpers

    # --- Unified type resolution ---
    # Single entry point for resolving typedef names to their underlying
    # primitive or struct/union type. All type-dependent decisions in codegen
    # should go through this method instead of inline typedef lookups.

    def _resolve_type(self, ty: str) -> str:
        """Resolve a type string through all typedef layers.

        Returns the final type string (e.g. "struct Foo", "int", "char*").
        If the type is a pointer typedef, returns "base*".
        If resolution fails, returns the input unchanged.
        """
        if not isinstance(ty, str) or not ty.strip():
            return ty
        b = ty.strip()
        # Already a known type — no resolution needed.
        if (b.startswith("struct ") or b.startswith("union ") or b.startswith("enum ")
                or "*" in b or b.startswith("array(")):
            return b
        _PRIMITIVES = {
            "void", "char", "unsigned char", "signed char",
            "short", "short int", "unsigned short", "unsigned short int",
            "signed short", "signed short int",
            "int", "unsigned int", "signed int",
            "long", "long int", "unsigned long", "unsigned long int",
            "signed long", "signed long int",
            "float", "double", "long double",
        }
        if b in _PRIMITIVES:
            return b
        # Try typedef resolution.
        if self._sema_ctx is not None:
            td = getattr(self._sema_ctx, "typedefs", {}).get(b)
            if td is not None:
                resolved = str(getattr(td, "base", "")).strip()
                is_ptr = getattr(td, "is_pointer", False)
                if is_ptr:
                    return resolved + ("*" if not resolved.endswith("*") else "")
                if resolved:
                    return self._resolve_type(resolved)
        return b

    # --- PIC-aware global symbol access ---
    # These methods centralize all global variable addressing so that
    # -fPIC support only needs to change these three methods.
    # Non-PIC: direct RIP-relative (symbol(%rip))
    # PIC: GOT-indirect (symbol@GOTPCREL(%rip) -> load through GOT)

    def _load_global_value(self, sym: str, reg: str, size: int = 8) -> None:
        """Load a global variable's value into reg, respecting PIC mode."""
        if self._pic:
            self._emit(f"  movq {sym}@GOTPCREL(%rip), %r11")
            if size == 1:
                self._emit(f"  movsbq (%r11), {reg}")
            elif size == 2:
                self._emit(f"  movswq (%r11), {reg}")
            elif size == 4:
                self._emit(f"  movslq (%r11), {reg}")
            else:
                self._emit(f"  movq (%r11), {reg}")
        else:
            if size == 1:
                self._emit(f"  movsbq {sym}(%rip), {reg}")
            elif size == 2:
                self._emit(f"  movswq {sym}(%rip), {reg}")
            elif size == 4:
                self._emit(f"  movslq {sym}(%rip), {reg}")
            else:
                self._emit(f"  movq {sym}(%rip), {reg}")

    def _store_global_value(self, sym: str, reg: str, size: int = 8) -> None:
        """Store reg into a global variable, respecting PIC mode."""
        # Map 64-bit register names to sub-register names for narrow stores.
        _sub = {
            "%rax": {1: "%al", 2: "%ax", 4: "%eax"},
            "%rcx": {1: "%cl", 2: "%cx", 4: "%ecx"},
            "%rdx": {1: "%dl", 2: "%dx", 4: "%edx"},
        }
        if self._pic:
            self._emit(f"  movq {sym}@GOTPCREL(%rip), %r11")
            if size == 1:
                sr = _sub.get(reg, {}).get(1, "%al")
                self._emit(f"  movb {sr}, (%r11)")
            elif size == 2:
                sr = _sub.get(reg, {}).get(2, "%ax")
                self._emit(f"  movw {sr}, (%r11)")
            elif size == 4:
                sr = _sub.get(reg, {}).get(4, "%eax")
                self._emit(f"  movl {sr}, (%r11)")
            else:
                self._emit(f"  movq {reg}, (%r11)")
        else:
            if size == 1:
                sr = _sub.get(reg, {}).get(1, "%al")
                self._emit(f"  movb {sr}, {sym}(%rip)")
            elif size == 2:
                sr = _sub.get(reg, {}).get(2, "%ax")
                self._emit(f"  movw {sr}, {sym}(%rip)")
            elif size == 4:
                sr = _sub.get(reg, {}).get(4, "%eax")
                self._emit(f"  movl {sr}, {sym}(%rip)")
            else:
                self._emit(f"  movq {reg}, {sym}(%rip)")

    def _load_global_addr(self, sym: str, reg: str) -> None:
        """Load the address of a global symbol into reg, respecting PIC mode."""
        if self._pic:
            self._emit(f"  movq {sym}@GOTPCREL(%rip), {reg}")
        else:
            self._emit(f"  leaq {sym}(%rip), {reg}")

    def _load_operand(self, operand: Optional[str], reg: str) -> None:
        if operand is None:
            self._emit(f"  movq $0, {reg}")
            return
        if operand.startswith("$"):
            self._emit(f"  movq {operand}, {reg}")
            return
        # If we ever see a bare identifier here, only treat it as a local if we
        # already have a stack slot for '@name'. Otherwise, keep it bare so it
        # can refer to a global symbol (or be handled by other cases).
        if operand.isidentifier() and self._is_local(f"@{operand}"):
            operand = f"@{operand}"
        if operand.startswith("%t"):
            # temps are also stack allocated lazily
            off = self._ensure_local(operand)
            # Best-effort: if we know the temp's type and it is narrower than
            # 64-bit, load it with correct width/extension.
            ty = self._var_types.get(operand, "")
            b = ty.strip() if isinstance(ty, str) else ""
            # IMPORTANT: pointer temps are 8-byte values.
            if isinstance(b, str) and ("*" in b or b == "ptr"):
                self._emit(f"  movq -{off}(%rbp), {reg}")
                return
            if b == "char" or b.startswith("char "):
                self._emit(f"  movsbq -{off}(%rbp), {reg}")
                return
            if b == "unsigned char" or b.startswith("unsigned char"):
                self._emit(f"  movzbq -{off}(%rbp), {reg}")
                return
            if b == "short" or b == "short int" or b.startswith("short"):
                self._emit(f"  movswq -{off}(%rbp), {reg}")
                return
            if b == "unsigned short" or b == "unsigned short int" or b.startswith("unsigned short"):
                self._emit(f"  movzwq -{off}(%rbp), {reg}")
                return
            if b == "int" or b.startswith("int ") or b.startswith("enum "):
                self._emit(f"  movslq -{off}(%rbp), {reg}")
                return
            if b == "unsigned int" or b.startswith("unsigned int"):
                # load 32-bit and zero-extend into destination
                if reg == "%rax":
                    self._emit(f"  movl -{off}(%rbp), %eax")
                    self._emit("  movl %eax, %eax")
                elif reg == "%rcx":
                    self._emit(f"  movl -{off}(%rbp), %ecx")
                elif reg == "%rdx":
                    self._emit(f"  movl -{off}(%rbp), %edx")
                elif reg == "%rsi":
                    self._emit(f"  movl -{off}(%rbp), %esi")
                elif reg == "%rdi":
                    self._emit(f"  movl -{off}(%rbp), %edi")
                elif reg == "%r8":
                    self._emit(f"  movl -{off}(%rbp), %r8d")
                elif reg == "%r9":
                    self._emit(f"  movl -{off}(%rbp), %r9d")
                elif reg == "%r10":
                    self._emit(f"  movl -{off}(%rbp), %r10d")
                elif reg == "%r11":
                    self._emit(f"  movl -{off}(%rbp), %r11d")
                else:
                    self._emit(f"  movl -{off}(%rbp), %eax")
                    self._emit("  movl %eax, %eax")
                    self._emit(f"  movq %rax, {reg}")
                return
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
                # IMPORTANT: pointers are 8-byte values; do not apply char/short
                # load/extension rules to e.g. "unsigned char*".
                if isinstance(b, str) and "*" in b:
                    self._emit(f"  movq -{off}(%rbp), {reg}")
                    return
                # signed char / char (treat plain `char` as signed in this backend)
                if b == "char" or b == "signed char" or b.startswith("char ") or b.startswith("signed char"):
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
                    # IMPORTANT: load into the requested destination register.
                    # Using %eax unconditionally can clobber a live value in
                    # %rax (e.g. binop operand1) when loading operand2.
                    if reg == "%rax":
                        self._emit(f"  movl -{off}(%rbp), %eax")
                        self._emit("  movl %eax, %eax")
                    elif reg == "%rcx":
                        self._emit(f"  movl -{off}(%rbp), %ecx")
                    elif reg == "%rbx":
                        self._emit(f"  movl -{off}(%rbp), %ebx")
                    elif reg == "%rdx":
                        self._emit(f"  movl -{off}(%rbp), %edx")
                    elif reg == "%rsi":
                        self._emit(f"  movl -{off}(%rbp), %esi")
                    elif reg == "%rdi":
                        self._emit(f"  movl -{off}(%rbp), %edi")
                    elif reg == "%r8":
                        self._emit(f"  movl -{off}(%rbp), %r8d")
                    elif reg == "%r9":
                        self._emit(f"  movl -{off}(%rbp), %r9d")
                    elif reg == "%r10":
                        self._emit(f"  movl -{off}(%rbp), %r10d")
                    elif reg == "%r11":
                        self._emit(f"  movl -{off}(%rbp), %r11d")
                    else:
                        # Fallback: use %eax and copy.
                        self._emit(f"  movl -{off}(%rbp), %eax")
                        self._emit("  movl %eax, %eax")
                        self._emit(f"  movq %rax, {reg}")
                    return
                # long/pointers/default
                self._emit(f"  movq -{off}(%rbp), {reg}")
                return
            sym = operand[1:]
            # If operand refers to a known function symbol, load its address.
            if sym in getattr(self, "_functions", set()):
                self._load_global_addr(sym, reg)
                return
            # If semantic analysis says this symbol is a function, load its
            # address (not its contents).
            if self._sema_ctx is not None:
                gty = getattr(self._sema_ctx, "global_types", {}).get(sym)
                if isinstance(gty, str) and gty.strip().startswith("function"):
                    self._load_global_addr(sym, reg)
                    return
            # Global objects: if this is an aggregate (struct/union/array), then
            # loading it as a scalar is almost always wrong. Prefer returning
            # its address so member/index operations can proceed correctly.
            ty = getattr(self._sema_ctx, "global_types", {}).get(sym) if self._sema_ctx is not None else None
            # Also check _var_types (seeded from gdecl/gdef for local statics).
            if ty is None:
                ty = self._var_types.get(operand)
            # Resolve typedef to underlying type for correct load width.
            if isinstance(ty, str):
                ty = self._resolve_type(ty)
            ga = getattr(self._sema_ctx, "global_arrays", {}) if self._sema_ctx is not None else {}
            is_aggregate = (
                (isinstance(ty, str) and (ty.strip().startswith("struct ") or ty.strip().startswith("union ") or ty.strip().startswith("array(")))
                or sym in ga
            )
            if is_aggregate:
                self._load_global_addr(sym, reg)
            elif isinstance(ty, str) and (ty.endswith("*") or "*" in ty):
                self._load_global_value(sym, reg, 8)
            else:
                # default scalar global: 32-bit signed int
                self._load_global_value(sym, reg, 4)
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
            b = self._resolve_type(ty)
        else:
            base = getattr(ty, "base", None)
            b = self._resolve_type(base.strip()) if isinstance(base, str) else ""
            if getattr(ty, "is_pointer", False):
                return 8
        if not b:
            return 8
        # pointers
        if "*" in b:
            return 8
        # structs/unions
        if (b.startswith("struct ") or b.startswith("union ")) and self._sema_ctx is not None:
            layout = getattr(self._sema_ctx, "layouts", {}).get(b)
            if layout is not None:
                try:
                    return int(getattr(layout, "size"))
                except Exception:
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

        if not s or not s.endswith("*"):
            return 8
        # peel exactly one '*' to get pointee type
        s = s[:-1]
        if not s:
            return 8
        # if pointee is itself a pointer, size is 8
        if s.endswith("*"):
            return 8
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

    def _pointee_is_unsigned(self, ptr_ty: object) -> bool:
        """Best-effort unsignedness for T* pointer types."""
        if ptr_ty is None:
            return False
        if isinstance(ptr_ty, str):
            s = ptr_ty.strip()
        else:
            base = getattr(ptr_ty, "base", None)
            s = base.strip() if isinstance(base, str) else ""
        if not s or "*" not in s:
            return False
        # peel trailing '*'
        while s.endswith("*"):
            s = s[:-1]
        return s.strip().startswith("unsigned ")

    def _store_result(self, result: Optional[str], reg: str) -> None:
        if result is None:
            return
        if result.startswith("%t"):
            off = self._ensure_local(result)
            # Store temps with width based on best-effort type info.
            ty = self._var_types.get(result, "")
            b = ty.strip() if isinstance(ty, str) else ""
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
        if result.startswith("@"):
            # local if it has a slot; otherwise global
            if self._is_local(result):
                off = self._ensure_local(result)
                ty = self._var_types.get(result, "")
                b = ty.strip()
                # IMPORTANT: pointers are always 8-byte values. Do not let
                # prefix checks like `startswith("unsigned char")` treat
                # "unsigned char*" as a 1-byte scalar.
                if isinstance(b, str) and "*" in b:
                    self._emit(f"  movq {reg}, -{off}(%rbp)")
                    return
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
            if isinstance(ty, str):
                ty = self._resolve_type(ty)
            if isinstance(ty, str) and (ty.endswith("*") or "*" in ty):
                self._store_global_value(sym, reg, 8)
            else:
                self._store_global_value(sym, reg, 4)
            return

    def _new_spill_name(self) -> str:
        """Generate a unique temp name for internal spill slots."""
        seq = getattr(self, "_spill_name_seq", 0)
        self._spill_name_seq = seq + 1
        return f"%t_spill_{seq}"

    def _ensure_local(self, sym: str, size: int = 8) -> int:
        if sym in self._locals:
            return self._locals[sym]


        # If we discover a new user-local (@name) after the initial decl scan,
        # allocate it after the declared locals AND after the fixed spill area.
        # Offsets in self._locals are positive numbers used as -off(%rbp).
        if sym.startswith("@"):
            # Allocate after all declared locals and after the reserved spill
            # area. This avoids overlapping with %t temps.
            base = int(getattr(self, "_locals_base", 0)) + int(getattr(self, "_spill_capacity", 0))
            # Also place after any already-created late locals (which also live
            # after the spill area).
            cur_max = max(self._locals.values()) if self._locals else 0
            off = max(base, cur_max) + 8
            self._locals[sym] = off
            return off

        # Allocate in the reserved spill area (no %rsp adjustment).
        if sym.startswith("%t"):
            # If we exhaust the reserved spill area, make a conservative
            # fallback by extending the function's frame in 16-byte chunks.
            # This still avoids emitting per-temp `subq $8, %rsp`.
            alloc = max(size, 8)
            if self._spill_used + alloc > self._spill_capacity:
                grow = 256
                if grow % 16 != 0:
                    grow += 16 - (grow % 16)
                self._spill_capacity += grow
                self._stack_size += grow
                # Update the already-emitted prologue frame size.
                # Prologue is: push %rbp; mov %rsp,%rbp; subq $N,%rsp
                for idx, line in enumerate(self.assembly_lines[:16]):
                    if line.strip().startswith("subq $") and line.strip().endswith(", %rsp"):
                        self.assembly_lines[idx] = f"  subq ${self._stack_size}, %rsp"
                        break
            self._spill_used += alloc
            # Spill slots live below all declared locals.
            # Place them at (locals_base + spill_used).
            base = int(getattr(self, "_locals_base", 0))
            self._locals[sym] = base + self._spill_used
            return self._locals[sym]

        # Late-introduced local (should be rare). Do NOT adjust %rsp in the body;
        # instead, conservatively assign a slot within the reserved spill area.
        if self._spill_used + 8 > self._spill_capacity:
            grow = 256
            if grow % 16 != 0:
                grow += 16 - (grow % 16)
            self._spill_capacity += grow
            self._stack_size += grow
            for idx, line in enumerate(self.assembly_lines[:16]):
                if line.strip().startswith("subq $") and line.strip().endswith(", %rsp"):
                    self.assembly_lines[idx] = f"  subq ${self._stack_size}, %rsp"
                    break
        self._spill_used += 8
        base = int(getattr(self, "_locals_base", 0))
        self._locals[sym] = base + self._spill_used
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
            self._load_global_addr(sym[1:], reg)
            return
        if sym.startswith("%t"):
            off = self._ensure_local(sym)
            self._emit(f"  leaq -{off}(%rbp), {reg}")
            return
        self._load_global_addr(sym, reg)

    def _resolve_member_offset(self, base_sym: str, member: str) -> int:
        """Return offset for `base_sym.member` using semantic layouts when available."""
        off, _ = self._resolve_member(base_sym, member)
        return off

    def _type_size_bytes(self, ty: str) -> int:
        """Best-effort size (bytes) for a type string."""
        b = self._resolve_type(ty)
        if b.startswith("struct ") or b.startswith("union "):
            layout = getattr(self._sema_ctx, "layouts", {}).get(b)
            return int(getattr(layout, "size", 0) or 0) if layout is not None else 0
        if "*" in b:
            return 8
        if b in {"char", "unsigned char", "signed char"}:
            return 1
        if b in {"short", "short int", "unsigned short", "unsigned short int", "signed short", "signed short int"}:
            return 2
        if b in {"int", "unsigned int", "signed int"} or b.startswith("enum "):
            return 4
        if b == "long double":
            return 16
        if b in {"long", "long int", "unsigned long", "unsigned long int", "signed long", "signed long int"}:
            return 8
        if "long long" in b:
            return 8
        if b == "float":
            return 4
        if b == "double":
            return 8
        return 8

    def _resolve_member(self, base_sym: str, member: str) -> Tuple[int, int]:
        """Return (offset, size_bytes) for `base_sym.member`."""
        decl_ty = self._var_types.get(base_sym)
        if isinstance(decl_ty, str) and decl_ty.strip().endswith("*"):
            decl_ty = decl_ty.strip()[:-1].strip()
        if not decl_ty and isinstance(base_sym, str) and base_sym.startswith("@") and self._sema_ctx is not None:
            decl_ty = getattr(self._sema_ctx, "global_types", {}).get(base_sym[1:])
        if self._sema_ctx is not None and decl_ty and hasattr(self._sema_ctx, "layouts"):
            layouts = getattr(self._sema_ctx, "layouts")
            resolved_ty = self._resolve_type(decl_ty)
            layout = layouts.get(resolved_ty)
            if layout is not None:
                off = layout.member_offsets.get(member)
                sz = layout.member_sizes.get(member)
                if off is not None and sz is not None:
                    return int(off), int(sz)
        if member == "x":
            return 0, 4
        if member == "y":
            return 4, 4
        return 0, 8

    def _resolve_bitfield(self, base_sym: str, member: str):
        """Return (bit_offset, bit_width) if member is a bit-field, else None."""
        decl_ty = self._var_types.get(base_sym)
        if isinstance(decl_ty, str) and decl_ty.strip().endswith("*"):
            decl_ty = decl_ty.strip()[:-1].strip()
        if not decl_ty and isinstance(base_sym, str) and base_sym.startswith("@") and self._sema_ctx is not None:
            decl_ty = getattr(self._sema_ctx, "global_types", {}).get(base_sym[1:])
        if self._sema_ctx is not None and decl_ty:
            resolved_ty = self._resolve_type(decl_ty)
            layout = getattr(self._sema_ctx, "layouts", {}).get(resolved_ty)
            if layout and getattr(layout, 'bit_fields', None) and member in layout.bit_fields:
                # Find bit_offset and bit_width from the Declaration objects
                # stored during layout computation
                members = getattr(layout, '_bf_info', None)
                if members and member in members:
                    return members[member]
        return None

    # Strings

    def _intern_string(self, s: str) -> str:
        if s in self._string_pool:
            return self._string_pool[s]
        lbl = f".LC{self._string_counter}"
        self._string_counter += 1
        self._string_pool[s] = lbl
        return lbl

    def _intern_float_literal(self, value: float, fp_type: str) -> str:
        if fp_type == "float":
            bits = _struct.pack('<f', value).hex()
        elif fp_type == "long double":
            bits = _struct.pack('<d', value).hex()
            key = f"double:{bits}"
            if key in self._float_pool:
                return self._float_pool[key]
            lbl = f".LF{self._float_counter}"
            self._float_counter += 1
            self._float_pool[key] = lbl
            return lbl
        else:
            bits = _struct.pack('<d', value).hex()
        key = f"{fp_type}:{bits}"
        if key in self._float_pool:
            return self._float_pool[key]
        lbl = f".LF{self._float_counter}"
        self._float_counter += 1
        self._float_pool[key] = lbl
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

    
