# 需求文档：统一声明符解析器

## 简介

将 `pycc/parser.py` 中分散的声明符（declarator）解析逻辑替换为一个统一的递归 `_parse_declarator()` 方法。当前实现在每个使用场景（函数定义、typedef、局部变量、参数、结构体成员）各自用 ad-hoc 逻辑处理声明符的子集，导致每遇到一个新的真实项目就暴露一个新的遗漏组合。

C89 声明符语法是递归的：
```
declarator = pointer? direct-declarator
direct-declarator = identifier
                   | '(' declarator ')'
                   | direct-declarator '[' constant-expr? ']'
                   | direct-declarator '(' parameter-list ')'
```

当前已知的遗漏：
- `typedef int arr_t[23]` — typedef 路径不支持数组后缀（已修复，但用 ad-hoc 补丁）
- `int (func_name)(params)` — 括号包裹的函数名（Lua 5.5 使用此模式防止宏展开）
- `void (*signal(int, void(*)(int)))(int)` — 复杂嵌套声明符

这是一次纯重构，不改变任何外部可观测行为。

## 术语表

- **声明符（Declarator）**: C 声明中指定名称和类型修饰符的部分，如 `*p`、`arr[10]`、`(*fp)(int)`
- **直接声明符（Direct-Declarator）**: 声明符去掉指针前缀后的部分
- **抽象声明符（Abstract-Declarator）**: 没有名称的声明符，用于 cast 和 sizeof

## 需求

### 需求 1：统一声明符解析方法

**用户故事：** 作为编译器开发者，我希望有一个统一的递归声明符解析方法，以便所有声明路径使用相同的逻辑。

#### 验收标准

1. THE Parser SHALL provide a single method `_parse_declarator()` that returns a structured result containing the name, pointer levels, array dimensions, and function parameter info
2. THE Parser SHALL handle pointer prefixes (`*`, `* const`, `* volatile`) in `_parse_declarator()`
3. THE Parser SHALL handle parenthesized declarators `(declarator)` recursively
4. THE Parser SHALL handle array suffixes `[N]`, `[]`, `[N][M]` in `_parse_declarator()`
5. THE Parser SHALL handle function parameter suffixes `(params)` in `_parse_declarator()`

### 需求 2：替换所有调用点

**用户故事：** 作为编译器开发者，我希望所有声明路径都使用统一的声明符解析方法。

#### 验收标准

1. THE Parser SHALL use `_parse_declarator()` in function definition/declaration parsing
2. THE Parser SHALL use `_parse_declarator()` in typedef parsing
3. THE Parser SHALL use `_parse_declarator()` in local variable declaration parsing
4. THE Parser SHALL use `_parse_declarator()` in parameter list parsing
5. THE Parser SHALL use `_parse_declarator()` in struct/union member parsing

### 需求 3：行为保持不变

**用户故事：** 作为编译器开发者，我希望重构后所有现有测试继续通过。

#### 验收标准

1. WHEN the full test suite is executed, THE Parser SHALL pass all tests without regression
2. THE Parser SHALL produce functionally equivalent AST nodes for all existing test cases

### 需求 4：新增语法支持

**用户故事：** 作为编译器开发者，我希望重构后能正确解析之前不支持的声明符形式。

#### 验收标准

1. THE Parser SHALL correctly parse parenthesized function names: `int (func)(int x)`
2. THE Parser SHALL correctly parse typedef arrays: `typedef int arr_t[23]` (consolidate existing ad-hoc fix)
3. THE Parser SHALL correctly parse complex nested declarators: `int (*(*fp)(int))[10]`
