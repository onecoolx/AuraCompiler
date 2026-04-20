# Roadmap: Multi-Target Code Generation

## 现状

AuraCompiler (pycc) 当前只支持 x86-64 SysV Linux 目标平台。代码生成器 (`pycc/codegen.py`) 直接发射 x86-64 汇编，所有目标相关的决策（寄存器名、调用约定、寻址模式、指令选择）都硬编码在一个文件中。

### 已实现的 PIC 支持

`-fPIC` 通过三个集中的辅助方法实现：
- `_load_global_value(sym, reg, size)` — 加载全局变量值
- `_store_global_value(sym, reg, size)` — 存储全局变量值
- `_load_global_addr(sym, reg)` — 加载全局符号地址

非 PIC 模式使用 `symbol(%rip)` 直接 RIP-relative 寻址；PIC 模式使用 `symbol@GOTPCREL(%rip)` 通过 GOT 间接寻址。

## 下一阶段：i386 后端

### 架构差异

| 维度 | x86-64 | i386 |
|------|--------|------|
| 寄存器 | 16 个 64 位通用寄存器 | 8 个 32 位通用寄存器 |
| 调用约定 | SysV AMD64 (参数在寄存器) | cdecl (参数全在栈上) |
| 指针大小 | 8 字节 | 4 字节 |
| 栈对齐 | 16 字节 | 4/16 字节 |
| PIC 寻址 | RIP-relative + GOTPCREL | GOT base register (%ebx) |
| 浮点 | SSE (xmm0-xmm7) | x87 FPU 栈 |
| 返回值 | rax/xmm0 | eax/ST(0) |

### 建议架构

```
pycc/
  codegen_x86_64.py    # 当前 codegen.py 重命名
  codegen_i386.py      # 新增 i386 后端
  target.py            # 共享接口和目标描述
  codegen.py           # 入口：根据 target 选择后端
```

#### target.py — 目标描述接口

```python
@dataclass
class TargetInfo:
    """目标平台的基本属性。"""
    name: str              # "x86_64", "i386", "aarch64"
    pointer_size: int      # 8 or 4
    stack_align: int       # 16 or 4
    endian: str            # "little"
    gp_arg_regs: list      # 参数传递寄存器列表
    gp_ret_reg: str        # 返回值寄存器

class TargetAddressing:
    """全局符号寻址策略（PIC/static）。"""
    def load_global_value(self, emit, sym, reg, size): ...
    def store_global_value(self, emit, sym, reg, size): ...
    def load_global_addr(self, emit, sym, reg): ...

class X86_64_Static(TargetAddressing): ...
class X86_64_PIC(TargetAddressing): ...
class I386_Static(TargetAddressing): ...
class I386_PIC(TargetAddressing): ...
```

#### codegen.py — 后端选择入口

```python
def create_codegen(target: str, optimize: bool, sema_ctx, pic: bool):
    if target == "x86_64":
        from pycc.codegen_x86_64 import CodeGenerator
        return CodeGenerator(optimize, sema_ctx=sema_ctx, pic=pic)
    elif target == "i386":
        from pycc.codegen_i386 import CodeGenerator
        return CodeGenerator(optimize, sema_ctx=sema_ctx, pic=pic)
    else:
        raise ValueError(f"unsupported target: {target}")
```

### 迁移步骤

1. **Phase 1**（当前完成）：`-fPIC` 支持，全局访问集中到 3 个辅助方法
2. **Phase 2**：将 `codegen.py` 重命名为 `codegen_x86_64.py`，创建 `codegen.py` 入口
3. **Phase 3**：提取 `TargetInfo` 和 `TargetAddressing` 到 `target.py`
4. **Phase 4**：实现 `codegen_i386.py`（cdecl 调用约定、32 位寄存器、x87 浮点）
5. **Phase 5**：CLI 添加 `-m32`/`-m64` 或 `--target=i386` 选项

### IR 层面

当前 IR 是目标无关的（操作数是符号名和临时变量，不是物理寄存器）。这个设计天然支持多后端 — 不同的 codegen 后端从同一个 IR 生成不同的汇编。

唯一需要注意的是 `_type_size` 和 `sizeof` — 指针大小在 i386 上是 4 而不是 8。这需要在 IR 生成阶段根据目标平台调整。建议将 `_type_size` 改为接受 `TargetInfo` 参数。

## 远期：其他目标平台

### AArch64 (ARM64)

- 31 个 64 位通用寄存器 (x0-x30)
- 参数在 x0-x7（最多 8 个）
- 浮点在 d0-d7
- PIC：ADRP + ADD 或 GOT

### RISC-V (rv64gc)

- 32 个 64 位通用寄存器
- 参数在 a0-a7
- PIC：auipc + GOT

### WebAssembly

- 栈机器，无寄存器
- 需要完全不同的 codegen 架构
- 可能需要 IR → Wasm 的直接翻译

## 设计原则

1. **IR 保持目标无关** — 不在 IR 中编码寄存器名或目标特定的操作
2. **每个目标一个 codegen 模块** — 不用 `if target == ...` 分支
3. **共享接口最小化** — 只抽象真正需要跨目标共享的部分（`TargetInfo`、`TargetAddressing`）
4. **渐进式迁移** — 不需要一次性重构，每个阶段都保持可编译可测试
