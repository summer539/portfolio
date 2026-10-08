---
name: export-excel
description: 某陶瓷企业排产-结果输出子技能。根据排产范围（单/双基地）调用对应固化脚本生成排产Excel。父技能：prod-schedule。
---

# 结果输出与Excel生成

**父技能：** prod-schedule（路由器调用）
**输入：** 排产结果JSON（单或双基地）
**输出：** xlsx文件绝对路径

## 🔴 核心铁律（最高优先级）

**必须使用固化脚本生成Excel，严禁自行编写代码。**

## 脚本选择

根据路由器传来的排产范围，选择对应脚本：

| 排产范围 | 脚本 | 输入 |
|---------|------|------|
| 双基地 | `scripts/generate_excel.py` | a-result.json + b-result.json |
| 仅某陶瓷企业 | `scripts/generate_excel_single.py a` | a-result.json |
| 仅B 基地 | `scripts/generate_excel_single.py b` | b-result.json |

## 操作步骤

### 步骤1：验证输入文件

```bash
# 双基地：两个文件都必须存在
ls -la /tmp/schedule-a-result.json /tmp/schedule-b-result.json

# 单基地：仅对应文件
ls -la /tmp/schedule-a-result.json   # 或 b-result.json
```

### 步骤2：执行固化脚本

```bash
# 双基地
python3 skills/prod-schedule/sub-skills/export-excel/scripts/generate_excel.py

# 单基地（某陶瓷企业）
python3 skills/prod-schedule/sub-skills/export-excel/scripts/generate_excel_single.py a

# 单基地（B 基地）
python3 skills/prod-schedule/sub-skills/export-excel/scripts/generate_excel_single.py b
```

### 步骤3：验证产出

```bash
ls -la 产出文件/对标*-智能排产方案-*.xlsx
```

使用 openpyxl 加载验证：每Sheet含图片数、列数、行数正确（16列/21列）。

### 步骤4：打印异常清单

从结果JSON中汇总打印（不依赖Excel）：

| 类别 | 必须打印前5条 |
|------|-------------|
| 🚨库存告急 | 品牌/编号/库存/日均/营销→AI |
| ⛔库存积压 | 品牌/编号/库存量 |
| 📈📉销量趋势异常 | 激增/骤降数量统计 |

### 步骤5：输出四段报告 + 文件路径

按父技能SKILL.md要求的四段格式输出（数据源→核心结果→关键异常→文件路径）。

## 输出产物

- **双基地**：`{workspace}/产出文件/对标{月}月{日}日-{规格}-智能排产优化方案-{YYYYMMDD}.xlsx`
  - Sheet1 某陶瓷企业·排产计划 / Sheet2 B 基地·排产计划 / Sheet3 汇总总览
- **单基地**：`{workspace}/产出文件/对标{月}月{日}日-{规格}-智能排产方案-{基地名}-{YYYYMMDD}.xlsx`
  - Sheet1 {基地}·排产计划 / Sheet2 汇总总览

## 固化脚本特性（了解即可，无需修改）

两个脚本共享相同的模板（16列品牌区块、底标/纸箱图片、库存标红、趋势颜色等），唯一区别：

| | generate_excel.py | generate_excel_single.py |
|---|---|---|
| 输入 | 两个JSON文件 | 一个JSON + 命令行指定基地 |
| 输出Sheet | 某陶瓷企业 + B 基地 + 汇总（3 Sheet） | 单基地 + 汇总（2 Sheet） |
| 汇总总览 | 双基地段 | 仅单基地段（另一段为空） |

## openpyxl 3.1.5 已知陷阱（勿踩）

| 陷阱 | 现象 | 正确做法 |
|------|------|---------|
| `img.anchor` 是字符串 | 无法设置偏移 | 用 `OneCellAnchor(_from=AnchorMarker(...), ext=...)` 替换 |
| `img.width=100` 不持久化 | 保存后仍是原始尺寸 | 用 PIL `resize()` → `BytesIO` → `Image(buf)` |
| `OneCellAnchor` 缺 `ext` | 图片 cx=0,cy=0 不可见 | 必须设置 `ext=XDRPositiveSize2D(cx=w*9525, cy=h*9525)` |
