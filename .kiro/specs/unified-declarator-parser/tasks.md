# 实现计划：统一声明符解析器

## 概述

将 `pycc/parser.py` 中 5+ 处分散的声明符解析逻辑替换为统一的递归 `_parse_declarator()` 方法。采用渐进式替换策略：先实现新方法，再逐步替换旧路径，每步都通过全量测试验证无回归。

## 任务

- [ ] 1. 实现 DeclaratorInfo 和 _parse_declarator
  - [ ] 1.1 定义 DeclaratorInfo 数据类
    - 包含 name, name_tok, pointer_level, pointer_quals, array_dims, is_function, fn_params 等字段
    - _Requirements: 1.1_
  - [ ] 1.2 实现 _parse_declarator 方法
    - 解析指针前缀（* 和限定符）
    - 解析直接声明符（标识符或括号递归）
    - 解析后缀（数组 [N] 和函数参数 (params)）
    - 支持 allow_abstract 参数（用于 cast/sizeof）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [ ] 1.3 实现 _apply_declarator 辅助方法
    - 将 DeclaratorInfo 应用到 base_type 上，构造正确的 Type 对象
    - 处理指针层数、数组维度、函数参数
    - _Requirements: 1.1_
  - [ ] 1.4 编写单元测试验证 _parse_declarator 独立正确性
    - 测试简单标识符、指针、数组、函数、括号包裹、嵌套组合
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3_

- [ ] 2. 替换 _finish_declarator
  - [ ] 2.1 用 _parse_declarator 替换 _finish_declarator 中的指针/数组/函数后缀解析
    - 保留初始化器解析逻辑
    - _Requirements: 2.3_
  - [ ] 2.2 运行全量测试验证无回归
    - _Requirements: 3.1_

- [ ] 3. 替换 _parse_external_declaration 函数/变量路径
  - [ ] 3.1 用 _parse_declarator 替换函数定义/声明的名称和参数解析
    - 包括括号声明符路径（当前 ~100 行 ad-hoc 代码）
    - _Requirements: 2.1, 4.1_
  - [ ] 3.2 运行全量测试验证无回归
    - _Requirements: 3.1_

- [ ] 4. 替换 typedef 路径
  - [ ] 4.1 用 _parse_declarator 替换 typedef 的名称/数组/函数指针解析
    - 合并之前的 ad-hoc typedef 数组修复
    - _Requirements: 2.2, 4.2_
  - [ ] 4.2 运行全量测试验证无回归
    - _Requirements: 3.1_

- [ ] 5. 替换 _parse_local_declaration
  - [ ] 5.1 用 _parse_declarator 替换局部变量声明的名称/指针/数组解析
    - _Requirements: 2.3_
  - [ ] 5.2 运行全量测试验证无回归
    - _Requirements: 3.1_

- [ ] 6. 替换 _parse_parameter_list
  - [ ] 6.1 用 _parse_declarator 替换参数声明的名称/指针/数组解析
    - _Requirements: 2.4_
  - [ ] 6.2 运行全量测试验证无回归
    - _Requirements: 3.1_

- [ ] 7. 替换结构体成员解析
  - [ ] 7.1 用 _parse_declarator 替换结构体/联合体成员的名称/数组解析
    - _Requirements: 2.5_
  - [ ] 7.2 运行全量测试验证无回归
    - _Requirements: 3.1_

- [ ] 8. 清理和最终验证
  - [ ] 8.1 删除被替换的旧代码
    - 删除 _finish_declarator 中被替代的逻辑
    - 删除 _parse_external_declaration 中被替代的 ad-hoc 括号处理
    - 删除 typedef 路径中被替代的 ad-hoc 数组处理
    - _Requirements: 3.1_
  - [ ] 8.2 编写新增语法支持的端到端测试
    - 括号包裹的函数名编译运行测试
    - 复杂嵌套声明符解析测试
    - _Requirements: 4.1, 4.2, 4.3_
  - [ ] 8.3 运行全量测试套件最终验证
    - _Requirements: 3.1, 3.2_

## 备注

- 每个替换步骤后必须运行全量测试
- 替换顺序从最简单的调用点开始（_finish_declarator），逐步到最复杂的（_parse_external_declaration）
- 如果某个替换步骤导致回归，先修复再继续
