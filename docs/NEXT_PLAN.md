# AuraCompiler — IR Architecture Refactoring Plan

> This document describes the multi-phase plan to introduce a two-level IR
> (HIR + LIR) architecture, enabling multi-backend support, platform-independent
> optimizations, and future multi-language frontends.
>
> Updated: 2026-05-18. Baseline: 2692 tests passing.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Frontend A (C89)    Frontend B (C99)    Frontend C (…)  │  language-specific
└────────────────────────────┬────────────────────────────┘
                             │ AST → HIR lowering
┌────────────────────────────▼────────────────────────────┐
│  Optimizer  (language-independent, platform-independent) │
│                                                         │
│  HIR: Module / Function / BasicBlock / Instruction      │
│  CFG, dominator tree, liveness analysis                 │
│  Optimization passes: const-fold, DCE, copy-prop, …    │
└────────────────────────────┬────────────────────────────┘
                             │ instruction selection + ABI lowering
┌────────────────────────────▼────────────────────────────┐
│  Backend  (language-independent, platform-specific)      │
│                                                         │
│  LIR: target instructions, virtual registers            │
│  Register allocation, instruction scheduling            │
│  Assembly emission (nearly 1:1 from LIR)                │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ x86_64/  │  │ aarch64/ │  │ riscv/   │  (future)    │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Language-specific? | Platform-specific? | Responsibility |
|-------|-------------------|--------------------|----------------|
| Frontend | Yes | No | Parse source → AST → lower to HIR |
| Optimizer (HIR) | No | No | Platform-independent analysis & optimization |
| Backend (LIR) | No | Yes | Instruction selection, regalloc, emit assembly |

### Directory Layout

```
pycc/
├── frontend/
│   └── c89/                # current C89 frontend
│       ├── lexer.py
│       ├── parser.py
│       ├── semantics.py
│       └── hir_lowering.py # AST → HIR translation
│
├── optimizer/              # mid-end: HIR + optimization passes
│   ├── hir.py             # HIRModule, HIRFunction, BasicBlock, HIRInst
│   ├── types.py           # CType hierarchy (existing, moved here)
│   ├── cfg.py             # CFG construction, dominator tree, liveness
│   └── passes/            # optimization pass framework + passes
│       ├── manager.py     # PassManager (extensible, plugin-friendly)
│       ├── const_fold.py  # constant folding
│       ├── dce.py         # dead code elimination
│       └── copy_prop.py   # copy propagation
│
├── backend/
│   ├── common/            # shared backend infrastructure
│   │   ├── regalloc.py    # generic register allocation algorithms
│   │   └── frame.py       # stack frame layout utilities
│   ├── x86_64/            # x86-64 backend (LIR + lowering + emit)
│   │   ├── lir.py         # x86-64 LIR instruction definitions
│   │   ├── lowering.py    # HIR → x86-64 LIR (instruction selection + ABI)
│   │   ├── regalloc.py    # x86-64 register allocation
│   │   ├── emit.py        # LIR → GAS assembly text
│   │   └── abi.py         # SysV AMD64 calling convention
│   └── aarch64/           # ARM64 backend (future)
│
└── driver.py              # compiler driver (frontend → optimizer → backend)
```

---

## Spec Breakdown

### Spec A: `hir-data-model` (10–12h)

**Goal**: Define the HIR core data structures and provide bidirectional bridging
with the existing flat IR instruction list.

**Deliverables**:
- `pycc/optimizer/hir.py`: HIRModule, HIRFunction, BasicBlock, HIRInst, Terminator
- HIR instruction set design (platform-independent operations):
  - Arithmetic: `add`, `sub`, `mul`, `div`, `mod`
  - Bitwise: `and`, `or`, `xor`, `shl`, `shr`
  - Comparison: `icmp`, `fcmp` (with condition codes: eq, ne, lt, le, gt, ge)
  - Memory: `load`, `store`, `alloca`, `gep` (get element pointer)
  - Control: `call`, `ret` (as terminators or instructions)
  - Conversion: `trunc`, `zext`, `sext`, `fptoui`, `fptosi`, `uitofp`, `sitofp`, `fpext`, `fptrunc`
  - Aggregate: `extractvalue`, `insertvalue`
- Terminator types: `Branch(cond, true_bb, false_bb)`, `Jump(target_bb)`, `Ret(value?)`, `Switch(val, cases, default)`, `Unreachable`
- `lift(instructions: List[IRInstruction]) -> HIRModule`: existing flat IR → HIR
- `flatten(module: HIRModule) -> List[IRInstruction]`: HIR → existing flat IR
- Property tests: `flatten(lift(instrs)) == instrs` roundtrip consistency
- Unit tests for each HIR instruction type

**Key constraint**: `flatten()` ensures the existing CodeGenerator continues to
work unchanged during the migration period.

---

### Spec B: `hir-generator` (14–16h)

**Goal**: Refactor the current `IRGenerator` to emit HIR directly instead of a
flat instruction list.

**Deliverables**:
- New `HIRGenerator` class (or refactored `IRGenerator`) that outputs `HIRModule`
- Internal state: `current_function: HIRFunction`, `current_block: BasicBlock`
- Block splitting logic: new block on `label`, end block on branch/jump/ret
- Global declarations → `HIRModule.globals`
- Transition support: `generate()` returns `HIRModule`; callers use `flatten()` for backward compat
- Move into `pycc/frontend/c89/hir_lowering.py` (frontend responsibility)
- All 2692+ existing tests must continue passing via the flatten bridge

---

### Spec C: `optimizer-framework` (12–14h)

**Goal**: Build the analysis infrastructure and optimization pass framework on
top of HIR. Implement a minimal set of demonstration passes. The framework must
be extensible — new passes can be added as Python modules or, in the future, as
native C extension modules for performance.

**Deliverables**:
- `pycc/optimizer/cfg.py`:
  - CFG construction (predecessors / successors for each BasicBlock)
  - Reachability analysis (detect unreachable blocks)
  - Dominator tree computation
  - Liveness analysis skeleton
- `pycc/optimizer/passes/manager.py`:
  - `PassManager` class with plugin-style registration
  - Pass interface: `class Pass(Protocol): def run(self, func: HIRFunction) -> HIRFunction`
  - Pass ordering / dependency declaration
  - Enable/disable individual passes via configuration
  - Designed to support future native (C/Cython/mypyc) pass modules via the same interface
- Demonstration passes (minimal, proof-of-concept):
  - `ConstantFolding`: evaluate constant arithmetic at compile time
  - `DeadCodeElimination`: remove unreachable blocks and unused assignments
- Property tests for CFG correctness
- Unit tests for each pass

**Extensibility requirements**:
- Adding a new pass = adding a new module that implements the `Pass` protocol
- PassManager discovers passes via explicit registration (not import magic)
- Pass interface is simple enough to implement in C via ctypes/cffi in the future

---

### Spec D: `x86-64-lir` (10–12h)

**Goal**: Define the x86-64 backend's LIR data structures and instruction set.

**Deliverables**:
- `pycc/backend/x86_64/lir.py`:
  - `LIRFunction`, `LIRBlock`, `LIRInst`, `MachineOperand`
  - x86-64 instruction enum (`X86Op`): MOV, ADD, SUB, IMUL, IDIV, CMP, TEST,
    JMP, Jcc, CALL, RET, PUSH, POP, LEA, MOVSS, MOVSD, ADDSS, ADDSD, etc.
  - Operand kinds: `VReg` (virtual register), `PReg` (physical register),
    `Imm` (immediate), `Mem` (memory reference), `Label`
- `pycc/backend/x86_64/abi.py`:
  - SysV AMD64 calling convention definition
  - Parameter registers (rdi, rsi, rdx, rcx, r8, r9 / xmm0–xmm7)
  - Return registers (rax, rdx / xmm0)
  - Caller-saved vs callee-saved register sets
- `pycc/backend/common/frame.py`:
  - Stack frame layout utilities (local slots, spill area, alignment)
- Unit tests for instruction encoding and ABI parameter classification

---

### Spec E: `hir-to-lir-lowering` (16–20h)

**Goal**: Implement the HIR → x86-64 LIR translation (instruction selection +
ABI lowering).

**Deliverables**:
- `pycc/backend/x86_64/lowering.py`:
  - Instruction selection: map each HIR op to one or more x86-64 LIR instructions
  - ABI lowering for function calls: place arguments in registers/stack per SysV AMD64
  - ABI lowering for function entry: move parameters from ABI registers to virtual registers
  - Type lowering: struct-by-value → register pairs or stack copy
  - Address computation: array/member access → LEA + offset
  - Float/integer register class separation
  - Comparison + branch pattern: `icmp` + `Branch` → `CMP` + `Jcc`
- Integration test: compile simple C programs through full pipeline (HIR → LIR → flatten → existing codegen as reference)
- All existing tests must pass (via flatten bridge during transition)

---

### Spec F: `x86-64-regalloc-emit` (14–16h)

**Goal**: Register allocation and assembly text emission for the x86-64 backend.

**Deliverables**:
- `pycc/backend/x86_64/regalloc.py`:
  - Linear scan register allocation (virtual registers → physical registers)
  - Spill handling: insert load/store for spilled virtual registers
  - Callee-saved register save/restore in prologue/epilogue
- `pycc/backend/x86_64/emit.py`:
  - LIR → GAS assembly text (nearly 1:1 translation)
  - Prologue/epilogue emission (stack frame setup/teardown)
  - String/float constant pool emission
  - Global variable emission
- `pycc/backend/common/regalloc.py`:
  - Generic liveness interval computation
  - Shared spill-slot allocation logic
- End-to-end test: compile programs through the full new pipeline without the flatten bridge
- Performance comparison: new pipeline vs old pipeline (correctness, not speed)

---

## Execution Order

```
Phase 1:  Spec A (HIR structure) + Spec D (LIR structure)    [parallel, pure data definitions]
Phase 2:  Spec B (HIR generator)                             [depends on A]
Phase 3:  Spec E (HIR → LIR lowering)                       [depends on A + D]
Phase 4:  Spec F (regalloc + emit)                           [depends on D + E]
Phase 5:  Spec C (optimizer passes)                          [depends on A, can run anytime]
```

After Phase 4, the compiler can run the full new pipeline:
`AST → HIR → x86-64 LIR → register allocation → assembly`.

Phase 5 (optimization) is additive — it improves output quality but is not
required for correctness.

---

## Migration Strategy

Throughout the migration, the existing flat-IR + CodeGenerator pipeline remains
functional via the `flatten()` bridge. This ensures:

1. All 2692+ existing tests continue passing at every step
2. New pipeline can be validated against old pipeline output
3. Old pipeline can be removed only after new pipeline passes all tests independently

The `flatten()` bridge is the safety net that makes this refactoring incremental
rather than big-bang.

---

## Total Estimated Effort

| Spec | Hours | Risk |
|------|-------|------|
| A: hir-data-model | 10–12 | Low |
| B: hir-generator | 14–16 | Medium |
| C: optimizer-framework | 12–14 | Low |
| D: x86-64-lir | 10–12 | Low |
| E: hir-to-lir-lowering | 16–20 | High |
| F: x86-64-regalloc-emit | 14–16 | High |
| **Total** | **76–90** | |
