C89 Implementation Roadmap (Living)

Last updated: 2026-02-25

目标
- 以可执行、可验证（tests）方式推进：
	1) **先补齐 C89 语言核心**（不必禁用 C99 扩展；后续会继续推进到 C99）
	2) 在语言核心完成后实现 **预处理器** + **多文件编译/链接**，可使用系统 glibc 编译大量 C89 程序
	3) 实现 **严格 C89 覆盖**（更接近标准条文的语义/诊断）
	4) 编译器驱动参数尽量与 **gcc/clang 兼容**
	5) 完善 **英文诊断**（清晰准确可读）

原则
- 每新增一个功能：必须配套新增测试（单元/集成），并确保 `pytest` 通过。
- 每完成一项：更新本文档状态（DONE/PARTIAL/TODO）并记录对应测试文件。

优先级功能清单（分阶段）

Legend: **DONE** = implemented + tested; **PARTIAL** = subset implemented + tested; **TODO** = not implemented.

阶段 1 — C89 语言核心（当前重点）

- **DONE** `typedef`（解析与符号表）：tests 覆盖 `tests/test_typedef.py`
- **DONE** `struct` / `union` 基本布局与成员访问：`tests/test_struct_union.py`, `tests/test_member_access.py`, `tests/test_member_semantics.py`
- **DONE** `enum`（含隐式计数）：`tests/test_enum.py`
- **PARTIAL** 存储类关键字：`extern`, `static`：`tests/test_storage_class.py`
- **DONE** 函数原型 + 定义（子集）：`tests/test_integration.py`
- **DONE** `goto` / labels：`tests/test_goto.py`
- **DONE** 控制流（if/while/do/for/switch）+ break/continue：多文件覆盖
- **DONE** `&&`/`||` 短路：`tests/test_short_circuit.py`
- **PARTIAL** 类型系统：整数提升/常见算术转换尚未完全实现（见阶段 2）

阶段 1.1 — 语言核心待补齐（TODO backlog）
- **TODO** 完整的声明器组合（函数指针、复杂嵌套声明器）
- **TODO** 初始化（尤其是聚合初始化：数组/struct 嵌套、`char[]` 字符串初始化）
- **TODO** 更完整的整型模型（`signed/unsigned/short/long` 语义一致性）
- **TODO** `const`/`volatile` 语义与更严格的 lvalue 规则

阶段 2 — 类型系统与转换（严格性提升）
- **TODO** 整数提升、常见算术转换（usual arithmetic conversions）
- **TODO** `const` / `volatile` 限定符的语义（可写性检查、指针限定符传播等）
- **PARTIAL** 数组类型（局部/全局、未指定大小、初始值）
- **DONE** `&&` / `||` 短路
- **PARTIAL** cast/sizeof 的类型推导与布局（当前只覆盖子集）

阶段 3 — 预处理器 / 多文件 / 链接（在语言核心完成后启动）
- **TODO** 预处理器：`#include`, `#define`, `#if/#ifdef/...`, `#line`, `#error`
- **TODO** 多源文件输入 → 生成 `.o` → 链接（使用系统 glibc）
- **PARTIAL** 全局/静态数据在 `.data`/`.bss`/`.rodata` 的布局与输出

阶段 4 — 严格 C89 覆盖 + 诊断与优化
- **TODO** 更严格的语义诊断（兼容声明、无效转换、不完整类型、未初始化使用等）
- **PARTIAL** 常量折叠与局部优化（目前为 minimal）

阶段 5 — gcc/clang 兼容驱动 + 合规性测试
- **TODO** 驱动参数尽量兼容 gcc/clang（`-c`, `-S`, `-E`, `-o`, `-I`, `-D`, `-U`, `-std=c89`, `-Wall`, `-Werror`, ...）
- **TODO** 与 `gcc -std=c89` 行为对照测试（feature matrix + corpus）

验收标准（每阶段）
- 解析：新增语法能被 `pycc` 成功解析为 AST
- 语义：常见合法程序正常通过语义检查，非法程序被拒绝并给出合理错误消息
- 生成：对应示例能编译、链接并在系统上正确运行（与 `gcc` 行为一致）

下一步建议（短期）
- 优先补齐 `&&` / `||` 短路（需要 IR 分支）并添加 side-effect 测试
- 推进更完整的类型系统（整数提升/算术转换、指针运算）

当前实现状态（pytest 通过：109 tests）
- `typedef`
- `struct`/`union` 基本布局与成员访问
- `enum` 定义与枚举常量
- `switch/case/default`（compare-chain lowering，支持 fallthrough）
- `sizeof`（最小子集：int/char/指针 等）
- C-style cast `(type)expr`（最小子集）
- `goto`/labels
- `&&` / `||` 短路

引用文件
- `pycc/parser.py`, `pycc/semantics.py`, `pycc/ast_nodes.py`, `pycc/codegen.py`

