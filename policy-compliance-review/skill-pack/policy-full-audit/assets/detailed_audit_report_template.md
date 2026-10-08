# 制度完整性和规范性审核报告

> 技能版本：{{skill_version}}；审核耗时：{{elapsed_seconds}}秒。
> 审核边界：检查制度名称、格式属性、必备条款和章节主题是否存在；不判断条款合法性、法规时点有效性或跨制度冲突。

## {{file_name}}

- 源文件：{{source_file}}
- 正文正式标题：{{body_title}}
- 制度类型：{{primary_type}}；名称层级：{{declared_level}}
- 完整性规则：{{selected_rules}}项；执行覆盖率：{{coverage_rate}}
- 完整性关注项：{{completeness_concern_count}}项；命名偏差：{{naming_deviation_count}}项；格式偏差：{{format_deviation_count}}项

### 必备条款逐项结果

| 编号 | 条款 | 状态 | 严重程度 | 证据位置 | 修改建议 |
|---|---|---|---|---|---|
| {{rule_id}} | {{item}} | {{status}} | {{severity}} | {{evidence_locations}} | {{suggestion}} |

### 章节逐项结果

| 编号 | 章节/主题 | 状态 | 严重程度 | 证据位置 | 修改建议 |
|---|---|---|---|---|---|
| {{rule_id}} | {{item}} | {{status}} | {{severity}} | {{evidence_locations}} | {{suggestion}} |

### 命名逐项结果

| 编号 | 检查项 | 状态 | 实际 | 要求 |
|---|---|---|---|---|
| {{rule_id}} | {{item}} | {{status}} | {{actual}} | {{required}} |

### 格式逐项结果

| 编号 | 检查项 | 状态 | 实际 | 要求 |
|---|---|---|---|---|
| {{rule_id}} | {{item}} | {{status}} | {{actual}} | {{required}} |

### 审核口径

- 命名以正文正式标题为准，文件名仅用于载体一致性检查。
- 自动编号从 OOXML 识别。
- 正文对齐和首行缩进不审核。
- 源文件不作修改。
- 偏差行按属性拆分（用户明确要求，2026-09-04，13:56 修订）：复合检查项只列实际与要求不一致的属性，"实际/要求"一一对应；**实际列只放不符合要求的属性值，一致属性不出现、不标注"✓"**，不整项照抄。
