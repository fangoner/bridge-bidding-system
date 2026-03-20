# 测试文件目录

本目录包含桥牌叫牌系统的所有测试和调试文件。

## 文件分类

### 核心集成测试
- `test_preprocess_integration.py` - 预处理程序与整个程序的集成测试（最重要）
- `test_tree_structure.py` - 树结构转换测试
- `test_tree_navigation.py` - 树结构导航测试

### 特定约定测试
- `test_1d_1h_1s.py` - 1D-1H约定测试
- `test_1d_1h_1s_debug.py` - 1D-1H约定调试版本
- `test_1c_1d.py` - 1C-1D约定测试
- `test_2d_2nt.py` - 2D-2NT约定测试
- `test_third_fourth_1h.py` - 第三四家开叫1H测试
- `test_third_fourth_1s.py` - 第三四家开叫1S测试
- `test_opening_1c.py` - 1C开叫测试

### 序列测试
- `test_all_sequences.py` - 所有叫牌序列测试
- `test_complete_sequence.py` - 完整序列测试
- `test_full_complete_sequence.py` - 完整序列测试
- `test_different_sequences.py` - 不同序列测试
- `test_user_sequence.py` - 用户序列测试
- `test_2d_keywords.py` - 2D关键词测试
- `test_2d_sequence.py` - 2D序列测试
- `test_1c_1s_1nt.py` - 1C-1S-1NT测试
- `test_1c_1s_1nt_full.py` - 1C-1S-1NT完整测试

### 导航测试
- `test_navigation.py` - 导航功能测试

### 调试文件
- `debug_tree_building.py` - 树结构构建调试
- `debug_tree_parsing.py` - 树结构解析调试
- `debug_tree_build.py` - 树结构构建调试
- `debug_tree_build2.py` - 树结构构建调试2
- `debug_navigation.py` - 导航调试
- `debug_navigation2.py` - 导航调试2
- `debug_navigation3.py` - 导航调试3
- `debug_partner_node.py` - 队友节点调试
- `debug_node_access.py` - 节点访问调试
- `debug_2h_key.py` - 2H关键词调试
- `debug_last_sequence.py` - 最后序列调试
- `debug_third_fourth.py` - 第三四家开叫调试

### 检查文件
- `check_1d_1h_1s_detailed.py` - 1D-1H-1S详细检查
- `check_regex.py` - 正则表达式检查
- `check_content.py` - 内容检查
- `check_indent.py` - 缩进检查
- `check_keywords.py` - 关键词检查
- `check_first_lines.py` - 首行检查
- `check_segments2.py` - 分段检查
- `check_third_fourth_content.py` - 第三四家开叫内容检查
- `check_bidding_keywords.py` - 叫牌关键词检查
- `check_dify_keywords.py` - Dify关键词检查

### 显示文件
- `show_1d_1h_content.py` - 显示1D-1H内容
- `show_1d_1h_lines.py` - 显示1D-1H行
- `show_1d_1h_tree.py` - 显示1D-1H树结构
- `show_1d_1h_tree2.py` - 显示1D-1H树结构2
- `show_opening_content.py` - 显示开叫内容
- `show_tree_structure.py` - 显示树结构

### 验证文件
- `verify_1d_1h_1s.py` - 验证1D-1H-1S

### 正则测试
- `test_regex.py` - 正则表达式测试

## 使用方法

### 运行核心集成测试
```powershell
python tests/test_preprocess_integration.py
```

### 运行树结构测试
```powershell
python tests/test_tree_structure.py
python tests/test_tree_navigation.py
```

### 运行特定约定测试
```powershell
python tests/test_1d_1h_1s.py
python tests/test_1c_1d.py
python tests/test_2d_2nt.py
```

### 运行第三四家开叫测试
```powershell
python tests/test_third_fourth_1h.py
python tests/test_third_fourth_1s.py
```

## 测试结果

所有测试用例都通过了：

1. **1D-1H-1S**: 正确导航到1S节点，提取10个后续叫品 ✓
2. **1C-1D-1H**: 正确导航到1H节点，提取12个后续叫品 ✓
3. **2D-2NT-3C**: 正确导航到3C节点，提取3个后续叫品 ✓
4. **第三四家开叫1H-2C**: 正确导航到2C节点，提取7个后续叫品 ✓
5. **第三四家开叫1S-2C-2D**: 正确导航到2D节点，提取6个后续叫品 ✓

## 注意事项

- 这些测试文件主要用于开发和调试阶段
- 生产环境不需要运行这些测试
- 核心测试`test_preprocess_integration.py`可用于验证系统功能
- 调试文件可以帮助理解代码逻辑和排查问题
