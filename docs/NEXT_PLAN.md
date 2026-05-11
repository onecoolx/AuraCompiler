# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated: 2026-05-11. Baseline: 2244 pycc tests passing, array/pointer distinction complete.

## 1. Complete expression type annotation in semantic analysis

**Problem**: _expr_type() returns None for compound expressions, causing false positives and code duplication.

**Proposed**: Bottom-up type annotation pass computing .resolved_type for every expression node based on C89 rules. All downstream consumers read .resolved_type.

**Benefits**: Eliminates false positives, simplifies IR gen, enables multi-language frontend support.

**Scope**: Large. 500-800 lines new + ~200 lines refactoring. Standalone spec.


## 2. Remove _var_types dictionary

**Problem**: Stringly-typed dictionaries (256 references across ir.py + codegen.py) duplicating TypedSymbolTable information.

**Dependencies**: Plan 1 recommended first (`.resolved_type` reduces string-to-CType guesswork).

**Scope**: Large refactor. 12-16h.


## 3. IR Architecture Refactoring: Structured, Typed, Multi-Layer IR

**Priority**: High. Core flaws: no Function/BasicBlock/CFG, target-dependent details in IR, weak typing.

**Proposed**: HIR (typed, structured) -> LIR (virtual registers, platform-specific) -> Assembly. 5 migration phases.

**Dependencies**: TargetInfo (done) for LIR lowering.

**Scope**: Large. 2000-3000 lines across 3-5 specs.


## 4. Preprocessor performance for large source files

**Problem**: Built-in preprocessor times out on sqlite3.c (250K lines). Forces use_system_cpp=True.

**Proposed**: Algorithm audit, PyPy compatibility, mypyc compilation.

**Scope**: Algorithm audit 1-2 days, PyPy trivial, mypyc 1 week.


## 5. Support 128-bit integers on x86-64

**Problem**: __uint128_t mapped to 64-bit (lossy). sqlite3 uses it for high-precision math.

**Proposed**: CType.INT128/UINT128, register-pair codegen using x86-64 mul/div.

**Dependencies**: Plan 3 (IR refactoring).

**Scope**: Medium. ~250 lines.


## 6. GCC extension: computed goto (labels as values)

**Problem**: Lua 5.5's VM core (`lvm.c`) uses GCC's computed goto extension (`&&label` to get label address, `goto *ptr` for indirect jump) for efficient opcode dispatch. Since pycc uses `gcc -E` for preprocessing and gcc defines `__GNUC__`, source code enables GCC extensions that pycc's parser doesn't support.

**Workaround**: Users can pass `-DLUA_USE_JUMPTABLE=0` to disable computed goto in Lua. Other projects may have similar fallback macros.

**Proposed implementation**:
1. **Parser**: Recognize `&&identifier` as a unary expression (GCC "address of label") returning `void *`.
2. **Parser**: Recognize `goto *expr;` as a computed goto statement.
3. **AST**: Add `LabelAddress` expression node and `ComputedGoto` statement node.
4. **IR**: Add `indirect_jump` instruction taking a register operand.
5. **Codegen**: Emit `jmp *%reg` for indirect jumps; emit `.quad .Llabel` for label address constants in dispatch tables.

**Alternative**: Define `__PYCC__` macro and undefine `__GNUC__` during preprocessing. But this breaks glibc headers which require `__GNUC__` for inline assembly, builtins, and type attributes.

**Scope**: Medium. ~150 lines parser + ~50 lines IR/codegen. Standalone feature.

**Priority**: High for real-world project compilation (Lua, CPython, Ruby all use computed goto).


## 7. Constant initializer architecture: type-driven recursive processing

**Problem**: The current constant initializer handling (`_emit_constant_initializer`, `_const_initializer_blob`, `_try_struct_member_init`) is a fallback chain of if-elif branches, each with its own type detection whitelist. Every new type combination (typedef pointer arrays, enum arrays, struct arrays with symbol refs, function pointer typedef arrays) requires patching a different branch's whitelist. This violates the "solve root cause, not symptoms" principle (经验 4).

**Symptoms encountered**:
- `opnames` (string pointer array + NULL): global path missing pointer array support
- `luaT_eventname` (local static string array): local path missing pointer array support → unified `_emit_constant_initializer`
- `boxmt` (struct array with symbol refs): `_try_struct_member_init` didn't handle arrays
- `searchers` (function pointer typedef array): pointer array detection didn't resolve typedefs
- Each fix was correct but incremental — the architecture keeps producing new gaps.

**Current mitigations**: Each branch now uses `_is_pointer_type`, `_resolve_elem_type`, `_is_struct_or_union_type` for type detection. `_emit_constant_initializer` unifies global and local static paths. `_struct_member_descs` is reusable for both single structs and struct arrays.

**Proposed design**: Replace the fallback chain with a single recursive, type-driven initializer processor:

```python
def _emit_static_init(self, gname, ty, init, sc):
    """Recursively emit constant initializer based on resolved type."""
    resolved = self._resolve_full_type(ty)  # resolves typedef, gets array info
    
    if resolved.is_array:
        for i, elem_init in enumerate(init.elements):
            self._emit_static_init(f"{gname}[{i}]", resolved.element_type, elem_init, sc)
    elif resolved.is_struct_or_union:
        for member, member_init in zip(resolved.members, init.elements):
            self._emit_static_init(f"{gname}.{member.name}", member.type, member_init, sc)
    elif resolved.is_pointer:
        # string literal, symbol ref, or null
        self._emit_pointer_constant(gname, init, sc)
    elif resolved.is_scalar:
        # integer, float, enum
        self._emit_scalar_constant(gname, resolved, init, sc)
```

**Benefits**: 
- No more whitelist gaps — any type combination is handled by recursion
- Single type resolution path (`_resolve_full_type`) instead of per-branch checks
- New types (e.g. array of pointers to structs) work automatically
- Much simpler code (~200 lines vs current ~500 lines across multiple methods)

**Dependencies**: Type system array/pointer distinction is now implemented — `Type.is_array` + `array_element_type` + `array_dimensions` are available for use.

**Scope**: Medium-large. ~300 lines rewrite of initializer handling. Standalone spec recommended.
