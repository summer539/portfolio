# 输出数据契约

## 1. 输出目录

默认一键审核会在指定目录生成：

```text
<output-dir>/
├─ 制度快速审核报告.md
├─ 制度完整性和规范性审核报告.md
├─ 制度快速审核汇总.json
├─ completeness/
│  ├─ <文档名>.json
│  ├─ 制度完整性审核报告.md
│  └─ 制度完整性审核汇总.json
└─ normative/
   ├─ <文档名>.json
   ├─ 制度规范性审核报告.md
   └─ 制度规范性审核汇总.json
```

同一输出目录中的固定文件名会被覆盖。批量任务或并发任务必须使用不同输出目录。

## 2. 汇总 JSON

`制度快速审核汇总.json` 是系统集成的主入口：

```json
{
  "audit_info": {
    "skill": "policy-full-audit",
    "skill_version": "1.0.0",
    "parsed_at": "ISO-8601 时间",
    "elapsed_seconds": 0.0,
    "profile": {}
  },
  "documents": 1,
  "completeness": [],
  "normative": []
}
```

`completeness` 和 `normative` 通过 `document.source_file` 关联。该字段是源文件绝对路径。

## 3. 完整性结果

每份文件包含以下主要字段：

| 字段 | 含义 |
|---|---|
| `document` | 文件名、绝对路径、正文正式标题 |
| `classification` | 主类型、置信度、名称层级、章节模板、组织范围和组织命中 |
| `mandatory_clause_checks` | 已选制度类型的必备条款逐项结果 |
| `chapter_checks` | 必要章节或章节主题逐项结果 |
| `coverage` | 规则选择、执行和覆盖率 |
| `parse_issues` | 解析异常；空数组表示未记录异常 |
| `extracted` | 解析出的段落、表格和格式证据 |

完整性状态：

| 状态 | 系统处理建议 |
|---|---|
| `存在` | 通过，有可定位证据 |
| `部分` | 已涉及但要素不足，列入整改 |
| `缺失` | 未发现对应内容，列入整改 |
| `不适用` | 经规则条件判断不适用，不计缺陷 |
| `待确认` | 类型、证据或专门清单不足，转人工确认 |

每个规则结果至少包含 `rule_id`、`item`、`status`、`severity`、`evidence` 和 `suggestion`。证据位置通常为 `para:<序号>` 或 `table:<序号>`。

## 4. 覆盖率约束

`coverage` 的成功条件必须同时满足：

- `selected_rules == executed_rules`；
- `coverage_rate == 1.0`；
- `duplicate_rule_ids` 为空；
- `missing_rule_ids` 为空。

覆盖率只证明已选择的代码规则被完整遍历，不代表制度合法、有效或实质充分。

## 5. 规范性结果

每份文件包含：

| 字段 | 含义 |
|---|---|
| `document` | 文件名和绝对路径 |
| `naming.title` | 从正文识别的正式标题 |
| `naming.declared_level` | 正文标题识别出的层级词 |
| `naming.checks` | N 系列命名规则全部结果 |
| `naming.deviations` | 未通过的可判定命名偏差 |
| `format.checks` | F 系列关键格式规则全部结果 |
| `format.deviations` | 未通过且格式属性可读的偏差 |
| `format.statistics` | 标题、正文、行距和章节统计 |
| `parse_issues` | 解析异常 |

规范性检查使用 `passed` 和 `readable`：

- `passed=true`：通过；
- `passed=false` 且 `readable=true`：不通过；
- `readable=false`：未识别，不自动判为违规。

## 6. 版本兼容

- 下游系统应优先按字段名解析，不依赖数组顺序或 Markdown 文案。
- 新增规则时保持既有 `rule_id` 含义不变；语义变化应使用新编号并提升技能版本。
- `skill_version` 用于识别规则实现版本；规则基线版本记录在对应参考文件中。
