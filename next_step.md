# Next Step Plans

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

**Proposed design**:
- Change the architecture so that `TypedSymbolTable` preserves per-function scopes across the IR-gen → codegen boundary
- Options: (a) don't pop scopes — snapshot them into a per-function map before popping; (b) serialize the scope into IR metadata; (c) keep a flat "all locals" dict alongside the scoped table
- Once codegen can resolve all local symbols via `TypedSymbolTable`, remove `_var_types` from both `IRGenerator` and `CodeGenerator`
- Remove all `_str_to_ctype` fallback paths in codegen's `_get_type`

**Scope**: Medium refactor. Depends on the initializer unification (plan 2) being complete first, since the initializer code heavily uses `_var_types`.
