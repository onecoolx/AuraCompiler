# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated after each major version milestone. Current baseline: cJSON 1.7.19 test suite passing, 1754 pycc tests passing.

## 1. Unify type size computation into a target-aware abstraction

**Problem**: Both IR layer (`ir.py`) and codegen layer (`codegen.py`) independently compute type sizes via `_type_size()` and `type_sizeof()`/`_ctype_sizeof()`, with hardcoded values like `int=4, long=8, char=1, pointer=8`. This works for x86-64 but breaks portability and blurs the boundary between semantic-level IR generation and platform-specific code generation.

**Current situation**:
- IR layer calls `_type_size` for: sizeof constant folding, pointer arithmetic scaling, local static array BSS sizing, struct layout member alignment
- Codegen layer calls `type_sizeof`/`_ctype_sizeof` for: stack frame allocation, load/store width selection, store_index/load_index element size, struct copy size

**Proposed design**:
- Introduce a `TargetInfo` class (e.g. `pycc/target.py`) that encapsulates all platform-dependent type sizes and alignments
- `TargetInfo` provides: `sizeof(CType) -> int`, `alignof(CType) -> int`, `pointer_size`, `register_width`, etc.
- Both IR generator and codegen receive the same `TargetInfo` instance
- IR layer uses `TargetInfo` for semantic operations (sizeof folding, pointer scaling)
- Codegen layer uses `TargetInfo` for instruction selection (mov width, stack allocation)
- Remove all hardcoded size constants from `_type_size`, `type_sizeof`, `_base_str_to_ctype` etc.
- Future: add `TargetInfo` presets for x86-64, x86-32, aarch64

**Scope**: Medium-large refactor. Should be a standalone spec.



## 2. Unify local initializer lowering into a recursive, type-driven function

**Problem**: Local variable initializer lowering in `_gen_statement` (Declaration branch of `pycc/ir.py`) is implemented as a series of ad-hoc `if/elif` branches, each handling one specific type×initializer combination:
- `char s[N] = "hi"` → byte-store loop
- `int a[N] = {1,2,3}` → `store_index` loop
- `int a[2][3] = {{...},{...}}` → flatten + `store_index`
- `struct S s = {...}` → `_lower_local_struct_initializer` (member-by-member `store_member`)
- `struct S arr[N] = {{...},{...}}` → **missing** (falls through to scalar path, produces garbage)
- Designated initializers → separate `_lower_local_array_designated_init` / `_lower_designated_struct_init`

Every new type×initializer combination (struct arrays, arrays of pointers to structs, nested multi-dim arrays of structs, etc.) requires adding another special-case branch. This is the classic "whitelist" anti-pattern described in lesson 4.

**Root cause**: The initializer lowering is not type-driven. It pattern-matches on surface syntax (array_size, is_pointer, type.base string) instead of recursively dispatching based on the target CType.

**Proposed design**:
- Introduce a single recursive entry point: `_lower_initializer(base_sym: str, base_is_ptr: bool, target_ctype: CType, init: Any) -> bool`
- Dispatch based on `target_ctype.kind`:
  - `ARRAY` → iterate elements, recursively call `_lower_initializer` for each element with `element_ctype`; use `addr_index` to get element address
  - `STRUCT/UNION` → iterate members, recursively call `_lower_initializer` for each member with `member_ctype`; use `addr_of_member`/`addr_of_member_ptr` to get member address
  - Scalar (`INT/CHAR/SHORT/LONG/FLOAT/DOUBLE/POINTER`) → `_gen_expr` + `store_member_ptr` or `store_index`
- Handle brace elision: when a nested `Initializer` is expected but a scalar is found, consume scalars sequentially for the sub-aggregate
- Handle designated initializers as a variant of the same recursive walk (designator resolves to a specific member/index, then recurse)
- Handle trailing zero-fill: when initializer elements are exhausted, zero-fill remaining members/elements
- The existing `_lower_local_struct_initializer` and `_lower_local_array_designated_init` become thin wrappers or are absorbed into the unified function
- Use `TypedSymbolTable` and `ast_type_to_ctype_resolved` to obtain the target CType from the declaration

**Benefits**:
- Automatically handles all type combinations: `struct S arr[N]`, `int arr[2][3][4]`, `struct { struct { int a[3]; } inner; } outer`, etc.
- New types (e.g. `_Complex`, `long long` in future) require zero initializer-lowering changes
- Eliminates 200+ lines of duplicated pattern-matching code
- Fixes the current `struct arr[N] = {{...}}` bug as a natural consequence

**Prerequisites**:
- TypedSymbolTable (done, from ir-type-annotations spec)
- `ast_type_to_ctype_resolved` (done)
- `_member_ctype_from_layout` (done)
- Codegen `store_member_ptr` float/double handling (done)

**Scope**: Medium refactor. Should be a standalone spec. Estimated ~300 lines of new code replacing ~500 lines of existing ad-hoc branches.


## 3. Remove `_var_types` dictionary (deferred from ir-type-annotations spec)

**Problem**: Both `IRGenerator._var_types` and `CodeGenerator._var_types` are stringly-typed dictionaries (`Dict[str, str]`) that duplicate type information already available in `TypedSymbolTable`. They exist because `TypedSymbolTable` scopes are popped after IR generation, leaving codegen with no local symbol type information.

**Current state**: The per-function `activate_function` mechanism is implemented and active — `TypedSymbolTable` supports `activate_function(name)` to restore a function's local scope for codegen, and `CodeGenerator.generate()` calls it before processing each function's IR. However, `_var_types` still exists as a fallback because not all codegen paths have been migrated to use `TypedSymbolTable` lookups yet. The dead first `_type_size_bytes(object)` duplicate in codegen has been removed; the surviving `_type_size_bytes(str)` is the canonical version.

**Proposed design**:
- Incrementally migrate codegen methods (`_get_type`, `_resolve_member_offset`, `_resolve_member_type`, `_type_size_bytes`, etc.) to use `TypedSymbolTable` as the primary type source
- Once all codegen paths use `TypedSymbolTable`, remove `_var_types` from both `IRGenerator` and `CodeGenerator`
- Remove all `_str_to_ctype` fallback paths in codegen's `_get_type`

**Scope**: Medium refactor. Depends on the initializer unification (plan 2) being complete first, since the initializer code heavily uses `_var_types`.


## 4. IR Architecture Refactoring: Structured, Typed, Multi-Layer IR

**Priority**: High. This is the most impactful architectural improvement for the compiler. Many current bugs (nested member access, struct array indexing, `&arr[i]` semantics, struct-by-value operations) stem from the IR being too low-level and unstructured.

### Problem Analysis

The current IR is a flat `List[IRInstruction]` of stringly-typed three-address code. It has three fundamental design flaws:

**Flaw 1: No program structure.** There is no `Function`, `BasicBlock`, or `CFG` abstraction. Functions are delimited by `func_begin`/`func_end` string markers in a linear list. Control flow is expressed via `label`/`jmp`/`jz`/`jnz` with no explicit edges between blocks. This makes CFG-based optimization (dead code elimination, constant propagation, register allocation) impossible.

**Flaw 2: Target-dependent details leak into IR.** The IR generator computes struct member offsets, array element scaling factors, and memory copy sizes at IR generation time. These are target-dependent (they depend on `sizeof`, alignment, ABI) and should be deferred to codegen. Examples:
- `store_member`/`load_member` carry member names but codegen must re-resolve offsets from layouts
- `addr_index` scaling is computed in IR gen using `_type_size` with hardcoded x86-64 sizes
- `struct_copy` carries `meta["size"]` in bytes
- `gdef_blob`/`gdef_struct` describe raw memory layout

**Flaw 3: Weak typing.** Operands are bare strings (`"%t0"`, `"@x"`, `"$42"`). Type information is carried via:
- `_var_types: Dict[str, str]` — stringly-typed, lossy, duplicated between IR gen and codegen
- `result_type: Optional[CType]` — bolted on as an optional field (our recent refactoring)
- `meta: dict` — ad-hoc bag of type hints (`member_type`, `fp_type`, `member_ctype`)

A well-designed IR should make types mandatory and structural, not optional metadata.

### Proposed Architecture

#### Layer 1: HIR (High-level IR) — replaces current IR

```
Program
├── GlobalDecl(name: str, type: CType, linkage: Linkage, initializer: Optional[Initializer])
└── Function(name: str, params: List[Param], return_type: CType, body: List[BasicBlock])
    ├── Param(name: str, type: CType)
    └── BasicBlock(label: str, instructions: List[Instruction], terminator: Terminator)
        ├── Instruction
        │   op: Op (enum, not string)
        │   result: Optional[TypedValue]
        │   operands: List[TypedValue]
        └── Terminator
            Branch(cond: TypedValue, true_bb: str, false_bb: str)
            Jump(target_bb: str)
            Return(value: Optional[TypedValue])
            Switch(value: TypedValue, cases: List[(int, str)], default: str)

TypedValue(name: str, type: CType)
```

Key properties:
- Every value has a mandatory `CType` — no stringly-typed operands
- `Function` is a first-class structure with explicit parameter list and return type
- `BasicBlock` has a label, a sequence of non-branching instructions, and exactly one `Terminator`
- Control flow is explicit: `Terminator` references target basic blocks by label
- `Op` is an enum, not a string — catches typos at definition time

#### Layer 2: LIR (Low-level IR) — new, between HIR and assembly

```
LFunction
├── LBasicBlock(label, instructions: List[LInstruction])
│   └── LInstruction
│       op: MachineOp (enum: MOV, ADD, SUB, IMUL, LEA, CALL, RET, CMP, Jcc, ...)
│       result: Optional[VReg]
│       operands: List[Operand]  # VReg | Immediate | MemRef | Label
│       width: int  # 1, 2, 4, 8 bytes
└── ...

VReg(id: int, type: CType)  # virtual register, infinite supply
MemRef(base: VReg, offset: int, index: Optional[VReg], scale: int)
```

Key properties:
- Virtual registers (infinite) instead of named temporaries
- Explicit memory references with base/offset/index/scale (x86 addressing modes)
- Instruction width is explicit (1/2/4/8 bytes)
- No struct member names — offsets are resolved during HIR → LIR lowering
- Platform-specific but not yet register-allocated

#### Lowering Pipeline

```
AST → HIR → (optimize HIR) → LIR → (register allocation) → Assembly
         ↑                      ↑
    type-driven,           target-dependent,
    platform-independent   uses TargetInfo
```

- **AST → HIR**: Type-driven lowering. Struct member access becomes `GetElementPtr(base, member_index)` (like LLVM's GEP). Array indexing becomes `GetElementPtr(base, index)`. No offset computation — that's deferred.
- **HIR optimization**: Dead code elimination, constant propagation, common subexpression elimination, all operating on the CFG.
- **HIR → LIR**: Target-dependent lowering. `GetElementPtr` is resolved to concrete byte offsets using `TargetInfo`. Struct-by-value operations are lowered to memcpy with concrete sizes. ABI calling conventions are applied (register assignment, stack spilling).
- **LIR → Assembly**: Straightforward 1:1 mapping from LIR instructions to assembly text. Register allocation (linear scan or graph coloring) assigns physical registers to virtual registers.

### Migration Strategy

This is a large refactoring that should be done incrementally:

**Phase 1**: Introduce `Function` and `BasicBlock` structures. The current linear `List[IRInstruction]` is split into functions and basic blocks. `func_begin`/`func_end` markers are replaced by `Function` objects. `label`/`jmp`/`jz`/`jnz` are replaced by `BasicBlock` terminators. Codegen iterates over `Function.basic_blocks` instead of scanning for markers.

**Phase 2**: Make `TypedValue` mandatory. Replace `result: Optional[str]` and `operand1/operand2: Optional[str]` with `result: Optional[TypedValue]` and `operands: List[TypedValue]`. Remove `_var_types` entirely — all type information lives in `TypedValue.type`. Remove `meta` dict — type information is structural.

**Phase 3**: Introduce `Op` enum. Replace `op: str` with `op: Op`. Define all operations as enum members with explicit operand count and type constraints.

**Phase 4**: Introduce LIR layer. Add `GetElementPtr` to HIR for struct/array access. Add HIR → LIR lowering pass that resolves offsets, applies ABI, selects instructions. Current codegen becomes the LIR → Assembly backend.

**Phase 5**: CFG-based optimization. Implement dead code elimination, constant propagation, and basic register allocation on the structured IR.

### Dependencies

- Plan 1 (TargetInfo) should be done first — LIR lowering needs it
- Plan 2 (initializer unification) can be done independently
- Plan 3 (_var_types removal) is subsumed by Phase 2

### Scope

Large refactoring. Should be broken into 3-5 standalone specs, one per phase. Estimated 2000-3000 lines of new code, replacing ~1500 lines of current IR generation and ~2000 lines of current codegen. The overall line count may increase slightly due to the additional abstraction layers, but each layer will be significantly simpler and more maintainable than the current monolithic design.


## 5. Refactor `_parse_type_specifier` into an unordered declaration-specifier collector

**Problem**: The current `_parse_type_specifier` assumes declaration specifiers appear in a fixed order — qualifiers (`const`/`volatile`) first, then a type keyword (`int`/`struct`/`enum`/typedef-name). But the C standard treats declaration specifiers as an unordered set. All of the following are legal and equivalent:

```c
const struct Foo *p;
struct Foo const *p;
volatile unsigned long x;
long unsigned volatile x;
const enum Color c;
```

Specific flaws in the current implementation:

1. The method saves `tok = self.current_token` at entry. A while loop consumes qualifiers, but subsequent branches still check `tok` (now stale) instead of `self.current_token`. This caused `const struct Foo` to be misparsed as `const int` (the `saw_any` fallback assumed implicit int).
2. After the fix, enum/struct/union branches use `self.current_token`, but the `tok` variable still exists. The `saw_any` branch uses `pass` to fall through, making control flow non-obvious. Future contributors adding new type branches could easily use `tok` by mistake.
3. Qualifiers (`const`/`volatile`) and integer modifiers (`unsigned`/`signed`/`short`/`long`) are consumed in the while loop, but type keywords (`int`/`struct`/`enum`) are handled outside via if/elif chains. This split makes combination handling inconsistent.

**Correct architecture**:

A single while loop collects all declaration specifiers, then a post-loop function constructs the Type from the collected information:

```python
def _parse_type_specifier(self) -> Type:
    quals = set()        # {'const', 'volatile'}
    sign = None          # 'signed' | 'unsigned' | None
    size = None          # 'short' | 'long' | None
    base = None          # 'int' | 'char' | 'void' | 'float' | 'double' | None
    tag_type = None      # ('struct', tag, members) | ('union', tag, members) | ('enum', tag, members)
    typedef_name = None  # str | None

    while self.current_token:
        v = self.current_token.value
        if v in {'const', 'volatile'}:
            quals.add(v)
            self.advance()
        elif v in {'unsigned', 'signed'}:
            sign = v
            self.advance()
        elif v in {'short', 'long'}:
            size = v
            self.advance()
        elif v in {'int', 'char', 'void', 'float', 'double'}:
            base = v
            self.advance()
        elif v in {'struct', 'union'}:
            tag_type = self._parse_struct_or_union_specifier()
        elif v == 'enum':
            tag_type = self._parse_enum_specifier()
        elif self.current_token.type == IDENTIFIER and v in self._typedefs:
            typedef_name = v
            self.advance()
        else:
            break

    return self._build_type_from_specifiers(quals, sign, size, base, tag_type, typedef_name)
```

**Benefits**:
- Eliminates the `tok` variable and `saw_any` flag — no more stale-token bugs
- All specifier orderings are automatically supported without per-permutation branches
- `struct`/`union`/`enum` parsing extracted into dedicated methods with clear responsibilities
- Adding new type keywords (e.g. `_Bool`, `long long`, `_Complex`) requires only one new elif

**Prerequisites**: None. Can be done independently.

**Scope**: Medium refactor. `_parse_type_specifier` is ~200 lines today; expected ~150 lines after refactoring (main method + `_build_type_from_specifiers` + extracted `_parse_struct_or_union_specifier`/`_parse_enum_specifier`). Requires full test suite validation.


## 6. Preprocessor performance: enable processing large source files without system cpp

**Problem**: The built-in Python preprocessor cannot handle large source files like sqlite3.c (250K lines). It times out after 5+ minutes, while `gcc -E` completes in 2-3 seconds. This forces pycc to use `use_system_cpp=True` by default, which introduces GCC-specific builtin expansions (`__builtin_va_arg`, `__builtin_va_start`, etc.) that the parser must then handle as special cases.

**Root cause**: The preprocessor is implemented in pure CPython, which is inherently slow for character-level text processing. Likely contributing factors include:
- O(n²) string concatenation patterns (`+=` instead of list-based building)
- Repeated regex compilation or backtracking in macro expansion
- Inefficient token scanning (character-by-character in Python)
- Deep recursion in macro expansion without memoization

**Proposed optimization path** (in order of effort vs. impact):

1. **Algorithm/data structure audit** (low effort, high impact)
   - Profile the preprocessor on a medium-sized file (e.g. 10K lines) to identify hotspots
   - Replace `str +=` patterns with `list.append` + `''.join`
   - Pre-compile all regex patterns
   - Use `dict`/`set` lookups instead of linear scans in macro tables and hidesets
   - Minimize redundant string copies in token pasting and stringization

2. **PyPy compatibility** (zero effort, 5-20x speedup)
   - Verify pycc runs correctly under PyPy3 (no C extension dependencies)
   - Add a `#!/usr/bin/env pypy3` shebang option or document PyPy usage
   - PyPy's JIT is particularly effective for the kind of tight loops in preprocessor code
   - Target: sqlite3.c preprocessing in under 30 seconds

3. **mypyc compilation** (medium effort, 3-10x speedup)
   - Add type annotations to `preprocessor.py` (and `lexer.py` if needed)
   - Compile with mypyc to produce a C extension module
   - No logic changes required, just annotations
   - Can be done incrementally (annotate hottest functions first)

**Success criteria**: Preprocess sqlite3.c (250K lines, ~30 `#include` expansions) in under 10 seconds on a typical development machine, without depending on system gcc.

**Prerequisites**: None. Can be done independently of other refactoring plans.

**Scope**: Varies by approach. Algorithm audit is a small task (1-2 days). PyPy validation is trivial. mypyc is medium (1 week). 


## 7. Support 128-bit integers on x86-64

**Problem**: GCC provides `__uint128_t` / `__int128` as compiler extensions for 128-bit integer arithmetic. Real-world code like sqlite3 uses them for high-precision intermediate computations (e.g. 64×64→128 bit multiplication in floating-point formatting). Currently pycc maps these to `unsigned long long` / `long long` (64-bit) in `strip_gcc_extensions()`, which allows compilation but produces incorrect results — the upper 64 bits are silently lost.

**x86-64 hardware support**: The CPU natively supports partial 128-bit operations:
- `mul` / `imul`: 64×64→128 result in `rdx:rax`
- `div` / `idiv`: 128÷64→64 quotient+remainder, dividend in `rdx:rax`
- Shifts and adds can be implemented with two-register sequences (`shld`/`shrd`)

**Proposed design**:

1. **Type system**: Add `CType.INT128` and `CType.UINT128` variants. `_type_size` returns `(16, 16)` for size and alignment.

2. **IR representation**: In the HIR refactoring (Plan 4), 128-bit values should be first-class typed values. Operations like `mul_wide` (64×64→128), `shr128`, `trunc128_to_64` can be explicit IR operations rather than generic `mul`/`shr`.

3. **Codegen (x86-64 LIR)**: Lower 128-bit operations to register-pair sequences:
   - Storage: `rdx:rax` or any two GPR pair
   - `mul_wide(a, b) → (hi, lo)`: emit `mov a, %rax; mul b` → result in `rdx:rax`
   - `shr128(val, 64)`: extract `rdx` (high half)
   - `trunc128(val)`: extract `rax` (low half)
   - `cast_to_128(val)`: zero-extend 64-bit to `rdx:rax` (`xor %rdx, %rdx`)
   - 128-bit add/sub: `add lo, lo; adc hi, hi`

4. **Parser**: Recognize `__uint128_t`, `__int128_t`, `__int128` as type keywords (remove the `strip_gcc_extensions` lossy mapping).

**Scope**: Medium. Depends on IR refactoring (Plan 4) for clean representation. The x86-64 codegen part is straightforward since the hardware instructions already exist. Estimated ~200 lines of codegen + ~50 lines of type system changes.


## 8. Semantic analysis: register struct layouts from all declaration forms

**Problem**: When compiling sqlite3.c, the semantic analyzer reports hundreds of "Unknown struct XXX for member access" errors. The root cause is that struct layouts are only registered when a struct is defined via a standalone `struct Tag { ... };` or `typedef struct Tag { ... } Name;` declaration. But sqlite3 extensively uses other declaration forms that also define struct members:

```c
// Form 1: static struct with inline definition and initializer
static struct Mem0Global {
    void *mutex;
    long alarmThreshold;
} mem0 = { 0, 0 };

// Form 2: struct defined inside a variable declaration
struct sqlite3AutoExtList {
    u32 nExt;
    void (**aExt)(void);
} sqlite3Autoext = { 0, 0 };

// Form 3: local struct definition inside function body
void f(void) {
    struct Sublist { int nList; int *aList; };
    struct Sublist s;
    s.nList = 1;  // "Unknown struct Sublist" error
}
```

In all these forms, the parser correctly parses the struct members and stores them in `_tag_members`. But the semantic analyzer only processes struct layouts when it encounters a `StructDecl` AST node at the top level. The variable declarations (`Declaration` nodes) that happen to contain inline struct definitions don't trigger layout registration.

**Additional semantic errors found in sqlite3**:
- "invalid application of sizeof to incomplete array" — sizeof on arrays declared as `[]` (flexible array members or extern arrays)
- "invalid cast to aggregate type" — casts involving struct types (e.g. `(Token){...}` compound literals)
- "pointer and non-pointer comparison" — comparisons between typed pointers and integer constants that should be allowed
- "conflicting return type" — false positives from typedef-resolved return types not matching
- "Assignment to non-modifiable lvalue" — false positives on struct member assignments through pointers

**Proposed design**:

The struct layout registration should be unified into a single mechanism that handles all declaration forms:

1. **Parser**: Already stores struct members in `_tag_members[tag_key]` for all forms. This is correct.

2. **Semantic analyzer**: Should register struct layouts whenever it encounters a type that references a tag with known members, regardless of the AST node type. Specifically:
   - When processing any `Declaration` node, check if `type.base` starts with `"struct "` or `"union "` and if `_tag_members` has members for that tag → register layout
   - When processing `TypedefDecl`, same check → register layout (already done)
   - When processing `StructDecl`/`UnionDecl`, register layout (already done)
   - The `_tag_members` dict from the parser should be passed to the semantic analyzer

3. **Layout registration should be idempotent**: If a struct is defined in one place and used in many, the layout should be registered once and reused.

**Scope**: Medium. The core change is in `semantics.py` — adding struct layout registration to the `Declaration` visitor. Estimated ~50 lines of semantic analyzer changes + fixing the false-positive errors listed above.

**Prerequisites**: None. Can be done as a standalone spec.


## 8. Complete expression type annotation in semantic analysis

**Problem**: The current semantic analyzer has a best-effort `_expr_type()` function that can only infer types for simple expressions (identifiers, literals, casts). For compound expressions (member access chains, array subscripts, function call return values, arithmetic/pointer operations, prefix/postfix increment), it returns `None`. This causes:

1. False positive errors — semantic checks reject valid code because they can't determine the expression type
2. Code duplication — IR generation and codegen must re-infer types independently
3. Incomplete checking — type compatibility checks are skipped when types are unknown

**Correct architecture**: Every expression node in the AST should have a `.resolved_type` attribute after semantic analysis. This is the standard approach used by GCC, Clang, and all production compilers. The type annotation pass should:

1. Walk the AST bottom-up after name resolution
2. For each expression node, compute its type based on C89 type rules:
   - Identifier → lookup in symbol table
   - IntLiteral → `int` (or `long`/`unsigned` based on value and suffix)
   - StringLiteral → `const char *`
   - BinaryOp → usual arithmetic conversions (C89 §6.2.1.5)
   - UnaryOp `&` → pointer to operand type
   - UnaryOp `*` → dereference: remove one pointer level
   - UnaryOp `++`/`--` → same type as operand
   - ArrayAccess → element type (remove array/pointer level)
   - MemberAccess → member type from struct layout
   - PointerMemberAccess → member type from struct layout
   - FunctionCall → return type from function signature
   - Cast → target type
   - Assignment → type of left side
   - Ternary → usual arithmetic conversions of 2nd and 3rd operands
   - SizeOf → `unsigned long` (size_t)
   - Comma → type of right operand
3. Store the result as `expr.resolved_type = Type(...)`
4. All downstream consumers (semantic checks, IR generation, codegen) read `.resolved_type` instead of re-inferring

**Benefits**:
- Eliminates all false positive semantic errors caused by unknown types
- IR generation becomes simpler — no need for `_var_types` dictionary or ad-hoc type guessing
- Enables proper type checking for all C89 type rules (integer promotions, pointer arithmetic, etc.)
- Foundation for multi-language support — each frontend annotates types according to its own rules, IR sees only annotated types

**Relationship to other plans**:
- Independent of IR refactoring (Plan 4) but complementary — annotated AST makes HIR generation trivial
- Subsumes `_var_types` removal (Plan 3) — codegen reads types from IR which reads from annotated AST
- Independent of preprocessor performance (Plan 6)

**Scope**: Large. Estimated 500-800 lines of new code for the type annotation pass, plus refactoring ~200 lines of existing `_expr_type` callers. Should be a standalone spec. The annotation pass itself is straightforward (mechanical application of C89 type rules), but integrating it with existing semantic checks and IR generation requires careful migration.
