# NEXT_PLAN 任务复杂度评估（内部）

> 评估日期：2026-04-27（第二次更新）
> 基线：1925 pycc tests passing，cJSON 1.7.19 编译通过，sqlite3 parser 100%
> 已完成：_parse_type_specifier 重构、TargetInfo 抽象

## 优先级总表

| 优先级 | 任务 | 复杂度 | 预估时间 | 依赖 |
|--------|------|--------|----------|------|
| 1 | 1. 初始化器统一 | 中 | 4-6h | 无 |
| 2 | 6. 表达式类型标注 | 高 | 8-12h | 无 |
| 3 | 4. 预处理器性能 | 中 | 4-12h | 无 |
| 4 | 2. 移除 _var_types | 高 | 6-8h | 任务 1 |
| 5 | 3. IR 架构重构 | 极高 | 40-60h | TargetInfo(done) |
| 6 | 5. 128 位整数 | 中 | 4-6h | 任务 3 |

任务 1、6、4 可独立并行推进，建议优先做。

---

## 任务 1：统一局部初始化器降低为递归类型驱动函数

**现状**：
- ir.py 中初始化器处理散布在多个分支（struct、array、scalar 各有独立路径）
- 经验 4 明确指出这是"白名单反模式"
- TypedSymbolTable 和 `ast_type_to_ctype_resolved` 已就绪
- TargetInfo 已就绪，可用于类型大小查询

**工作量**：写递归 `_lower_initializer(ctype, init_list)` 替换 ~500 行 ad-hoc 分支

**难点**：brace elision 和 designated initializer 的边界情况

**复杂度**：中等 | **预估**：4-6 小时 | **依赖**：无

---

## 任务 2：移除 _var_types 字典

**现状**：
- `_var_types` 在 ir.py ~40 处引用，codegen.py ~50 处引用（共 ~90 处）
- 代码注释明确说：codegen 仍依赖 `_var_types` 做函数局部类型查找
- 原因：TypedSymbolTable 的 scope 在 IR gen 结束后就 pop 了，codegen 看不到
- TargetInfo 迁移没有减少 _var_types 的使用量，因为 _var_types 是类型标注而非大小查询

**工作量**：
1. 改 TypedSymbolTable 架构让 per-function scope 跨 IR-gen → codegen 边界持久化
2. 逐个替换 ~90 个 `_var_types` 引用点

**复杂度**：高 | **预估**：6-8 小时 | **依赖**：任务 1

---

## 任务 3：IR 架构重构（HIR → LIR → Assembly）

**现状**：
- IR 是扁平 `List[IRInstruction]`，无 Function/BasicBlock/CFG 结构
- `IRInstruction` 是 dataclass，字段全是 `Optional[str]`
- ir.py + codegen.py 合计 8000+ 行全部依赖这个扁平结构
- TargetInfo 已完成，LIR lowering 的前置条件已满足

**工作量**：需 3-5 个独立 spec，每个 spec 都是中等规模重构

**复杂度**：极高 | **预估**：40-60 小时（分 5 阶段，每阶段 8-12h）| **依赖**：TargetInfo（已完成）

---

## 任务 4：预处理器性能优化

**现状**：
- preprocessor.py ~1200 行
- 内置预处理器在 sqlite3.c（250K 行）上超时
- 目前靠 `use_system_cpp=True` 绕过

**工作量**：
- 算法审计（找热点、优化宏展开/hideset 算法）：4-6h
- PyPy 兼容性：基本免费
- mypyc 编译：8-12h

**复杂度**：中等 | **预估**：4-12 小时（取决于做到哪一步）| **依赖**：无

---

## 任务 5：128 位整数支持

**现状**：
- `__uint128_t` 当前映射为 64 位（有损）
- sqlite3 用它做高精度数学
- 被任务 3 阻塞

**工作量**：CType 新增 INT128/UINT128，codegen 实现寄存器对运算，约 250 行

**复杂度**：中等 | **预估**：4-6 小时（假设任务 3 已完成）| **依赖**：任务 3

---

## 任务 6：完整表达式类型标注

**现状**：
- `_expr_type()` ~120 行，只处理部分 AST 节点
- 已覆盖：Cast、Identifier、UnaryOp、MemberAccess、FunctionCall、ArrayAccess、部分 BinaryOp
- 未覆盖：复合表达式、三元运算符、逗号运算符、完整 BinaryOp 类型推导
- 复合表达式返回 None，导致下游误报

**工作量**：
1. 覆盖所有 C89 表达式类型推导规则（UAC、整数提升、指针算术等）
2. 在 AST 上附加 `.resolved_type`
3. 修改所有下游消费者从调用 `_expr_type()` 改为读 `.resolved_type`

**复杂度**：高 | **预估**：8-12 小时 | **依赖**：无
