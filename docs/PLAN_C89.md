# C89 推进计划（按模块拆分）

本文档用于：
- 汇总当前 AuraCompiler（`pycc`）已支持的 C89 子集能力
- 按模块列出缺口与依赖
- 给出可执行的分阶段推进计划（每阶段：先加测试 → 实现 → `pytest -q` 全绿）

> 约定：本项目当前采用最小 IR（字符串操作数）与渐进式类型信息（stringly-typed）。本计划避免大规模架构重写；只在必要处补足信息传递与局部抽象。

---

## 0. 当前实现状态（以现有 tests 为准）

### 0.1 词法/解析
- 基本 token/运算符：`+ - * / % == != < > <= >= && || ! ~ & | ^ << >>` 等（见 `tests/test_lexer.py`）
- 基本语句：`if/else/while/do-while/for/switch/case/default/break/continue/return/goto/label`（多处集成测试覆盖）
- 表达式：二元/一元、三目、赋值、函数调用、数组下标、成员访问、cast、sizeof（最小子集）
- 类型说明符（最小实现）：`char/int/void` + `short/long/signed/unsigned`（string 归一化）
- 聚合声明：`struct/union/enum` 的声明形态（含匿名 enum）
- 存储类（最小实现）：`extern/static`（见 `tests/test_storage_class.py`）

### 0.2 语义（最小实现）
- 作用域追踪、重复声明检测、未声明标识符的 best-effort 检查
- `typedef` 注册与解析（见 `tests/test_typedef.py`）
- `struct/union` 布局计算与成员偏移/尺寸（见 `tests/test_struct_union.py`、`tests/test_member_semantics.py`）
- `enum` 常量表达式求值（最小：整型常量表达式）与枚举常量替换（见 `tests/test_enum.py`）
- 记录全局对象类型：`SemanticContext.global_types`

### 0.3 IR / Codegen
- IR：最小 TAC 指令集（`mov/binop/unop/call/ret/label/jmp/jz/jnz/...`），并支持 `load/store_index` 与 `load/store_member`
- x86-64 SysV：函数序言/尾声、调用约定、全局/局部变量、`.rodata` 字符串字面量
- `&&/||`：IR 级短路 lowering（见 `tests/test_short_circuit.py`）
- `sizeof`：`sizeof(type)` 走 `_type_size()`，`sizeof expr` 仍是保守 fallback（见 `tests/test_sizeof.py`）
- 整数类型：已覆盖部分 load/store 宽度与无符号比较（见 `tests/test_int_types.py`）

---

## 1. C89 模块缺口表（按优先级/依赖拆分）

> 下面按“能否通过更多真实 C89 程序”的影响排序；每条都给出依赖与建议测试形式。

### A. 预处理器（PP）【最大缺口】
- 缺口：`#include/#define/#if/#ifdef/#pragma` 等
- 依赖：几乎所有真实世界 C89 源码都需要 PP
- 建议阶段：最后单独做（工作量大），或先用系统 `cpp` 作为外部预处理（也可写测试覆盖 driver 行为）

### B. 声明器/类型系统（declarator/type）【最大缺口】
- 复杂声明器：函数指针、数组 of 指针、指针 to 数组、括号改变优先级
- 更完整的类型合并/兼容性（重复声明、函数原型合并、参数类型匹配）
- `const/volatile` 的传播与限制（你计划 #4）
- `auto/register`（你计划 #3；语义层较简单，但要体现存储类规则）
- 位域（bit-field）

### C. 表达式语义/转换规则（integer/pointer conversions）
- 整数提升与 usual arithmetic conversions（当前只做了比较的最小 unsigned 处理；算术/位移/条件表达式仍不完整）
- 指针算术（你计划 #2）：`p+1`、`p[i]` 的等价性更系统地覆盖（目前 `p[i]` 依赖 `load_index`，但类型驱动的元素大小规则还不完整）
- `sizeof(expr)` 的类型推导（目前保守）

### D. 初始化器（initializers）
- 局部/全局聚合初始化：数组/struct 的初始化列表（含嵌套）
- 未指定大小数组的初始化推导（`int a[] = {1,2,3};`）
- 全局初始化常量表达式限制（更严格）

### E. 翻译单元/链接（multi-TU）
- 多文件编译链接测试（`extern` 跨文件、重复定义诊断、弱符号等）
- 这可以先用集成测试做“驱动层”能力验证

---

## 2. 分阶段推进计划（每阶段都要测试驱动 + 全绿）

### Phase 0（当前）
- 基线：`pytest -q` 全绿（已达成）

### Phase 1：指针算术（按你的顺序 #2）
目标：
- 支持 `T* p; p+1; p-1; p[i]` 的元素大小缩放（`sizeof(T)`）
- 支持 `p - q`（同一数组内，返回元素个数；可先做最小子集）
建议新增测试：
- `char*` 与 `int*` 的 `p+1` 读写不同地址（通过访问数组元素验证）
- `int a[3]; int* p=a; p[1]=...;` 与 `*(p+1)` 行为一致
可能改动文件：`pycc/ir.py`, `pycc/codegen.py`, 视需要少量 `pycc/semantics.py`

### Phase 2：更完整的整数转换（继续补齐 #1 的尾巴）
目标：
- 算术/位运算/移位对 unsigned 的一致行为（不仅是比较）
- 更严格的截断与符号扩展（赋值、返回、参数）
建议新增测试：
- `unsigned int` 的右移是逻辑移位（或在本项目里明确定义目标行为并测试）
- 混合 signed/unsigned 的 `+,-` 结果与比较

### Phase 3：`auto/register`（#3）
目标：
- 解析与语义接受 `auto/register`（C89 允许，但多数场景等价于默认 auto；register 有取地址限制）
建议新增测试：
- `register int x; int *p=&x;` 应报错（若你愿意做该语义）或先暂不支持并给出错误

### Phase 4：`const/volatile`（#4）
目标：
- 解析/类型携带 qualifier
- `const` 对赋值的限制（最小：`const int x=1; x=2;` 报错）

### Phase 5：初始化器（D）
目标：
- 数组/struct 初始化列表（局部优先）
- 全局聚合初始化（`.data` 布局）

### Phase 6：多翻译单元（E）
目标：
- driver 支持多输入文件并链接
- extern 跨文件测试

### Phase 7：预处理器（A）
两种路线：
1) 集成系统 `cpp`（快，但依赖环境）；
2) 自研最小 PP（慢但可控）。

---

## 3. 执行规则（工程质量）
- 每个 Phase 内拆成若干小步；每小步：
  1) 先加测试（确保失败）
  2) 实现/修复
  3) `pytest -q` 全绿
- 若出现回归：优先修复回归并恢复全绿，再继续。
