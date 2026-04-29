# 设计文档：统一声明符解析器

## 概述

实现一个统一的 `_parse_declarator()` 方法，替换 parser.py 中 5+ 处分散的声明符解析逻辑。核心思想是严格按照 C89 语法规则递归解析声明符，然后让所有使用场景（函数定义、typedef、变量声明、参数、结构体成员）都调用这个统一方法。

## 当前问题

parser.py 中声明符解析分散在以下位置：
1. `_parse_external_declaration` (~200 行) — 函数定义/全局变量，含括号声明符的 ad-hoc 处理
2. `_parse_external_declaration` typedef 分支 (~80 行) — typedef 名称 + 数组/函数指针后缀
3. `_parse_local_declaration` (~250 行) — 局部变量，含括号声明符
4. `_parse_parameter_list` (~170 行) — 函数参数
5. `_parse_struct_or_union_specifier` 成员解析 (~100 行) — 结构体成员
6. `_finish_declarator` (~150 行) — 共享的后缀解析（数组、函数参数）

每个位置各自处理指针前缀、括号、数组后缀、函数参数的子集，导致：
- 代码重复 ~500 行
- 每个新的声明符组合都可能在某个路径上失败
- 修复一个路径不会自动修复其他路径

## 设计

### DeclaratorInfo 数据结构

```python
@dataclass
class DeclaratorInfo:
    """Result of parsing a C declarator."""
    name: Optional[str] = None           # 声明符名称（抽象声明符为 None）
    name_tok: Optional[Token] = None     # 名称 token（用于行号）
    pointer_level: int = 0               # 指针层数
    pointer_quals: List[Set[str]] = field(default_factory=list)  # 每层指针的限定符
    array_dims: List[Optional[int]] = field(default_factory=list)  # 数组维度
    is_function: bool = False            # 是否是函数声明符
    fn_params: Optional[List[Declaration]] = None  # 函数参数列表
    fn_is_variadic: bool = False         # 是否是变参函数
    is_paren_wrapped: bool = False       # 名称是否被括号包裹
```

### _parse_declarator() 方法

```python
def _parse_declarator(self, allow_abstract: bool = False) -> DeclaratorInfo:
    """Parse a C declarator (recursive).
    
    Grammar:
        declarator = pointer? direct-declarator
        pointer = '*' type-qualifier-list? pointer?
        direct-declarator = identifier
                          | '(' declarator ')'
                          | direct-declarator '[' constant-expr? ']'
                          | direct-declarator '(' parameter-list ')'
    
    Args:
        allow_abstract: If True, the name is optional (for casts, sizeof).
    
    Returns:
        DeclaratorInfo with all parsed information.
    """
```

实现步骤：
1. 解析指针前缀：消费 `*` 和限定符（const/volatile/restrict），记录层数和限定符
2. 解析直接声明符：
   - 如果是 `(`：递归调用 `_parse_declarator()`，消费 `)`
   - 如果是标识符：记录名称
   - 如果 `allow_abstract` 且都不是：返回无名声明符
3. 解析后缀（循环）：
   - `[N]`：记录数组维度
   - `(params)`：解析参数列表，标记为函数声明符

### 调用点替换

每个调用点的模式：
```python
# 旧代码（每处 50-200 行 ad-hoc 逻辑）
base_type = self._parse_type_specifier()
# ... ad-hoc pointer/name/array/function parsing ...

# 新代码（统一调用）
base_type = self._parse_type_specifier()
decl_info = self._parse_declarator()
# 用 decl_info 构造 Type/Declaration/FunctionDecl
```

### 从 DeclaratorInfo 构造 AST 节点

新增辅助方法 `_apply_declarator(base_type, decl_info)` 将声明符信息应用到基础类型上：
- 指针层数 → `Type.pointer_level`
- 数组维度 → `Declaration.array_size/array_dims`
- 函数参数 → `FunctionDecl.parameters`

## 迁移策略

渐进式替换，每步验证全量测试：

1. 实现 `_parse_declarator()` 和 `DeclaratorInfo`（不替换任何调用点）
2. 替换 `_finish_declarator()`（最简单的调用点，已经是共享方法）
3. 替换 `_parse_external_declaration` 的函数/变量路径
4. 替换 typedef 路径（合并之前的 ad-hoc 数组修复）
5. 替换 `_parse_local_declaration`
6. 替换 `_parse_parameter_list`
7. 替换结构体成员解析
8. 删除旧代码

## 测试策略

- 现有 2066 个测试作为回归基线
- 新增测试覆盖之前不支持的声明符形式：
  - 括号包裹的函数名 `int (func)(int)`
  - 复杂嵌套 `int (*(*fp)(int))[10]`
  - typedef 数组（合并现有测试）
