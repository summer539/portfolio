# 制度一致性审核报告

> 审核基线：制度一致性审核清单.md（V1.0）
> 审核模式：{{mode}}
> 基准制度：{{baseline_document}}（上下级审核以最上级为基准，重点呈现下级制度的冲突）
> 审核日期：{{audit_date}}
> 审核耗时：{{elapsed_seconds}}秒
> 审核对象：{{document_count}}份文件

## 审核概览

- 文件数：{{document_count}}
- 内部冲突：{{internal_conflict_count}}项
- 跨制度冲突：{{cross_conflict_count}}项
- 硬冲突：{{hard_conflict_count}}项
- 软不一致：{{soft_inconsistency_count}}项
- 待确认：{{pending_count}}项

## 审核文件清单

| 序号 | 文件名 | 制度名称 | 条款数 |
|---|---|---|---|
| {{seq}} | {{file_name}} | {{title}} | {{article_count}} |

## 冲突清单（按严重度降序）

| 编号 | 冲突点 | 涉及制度/条款 | 维度 | 类型 | 严重度 | 证据摘录 | 修改建议 |
|---|---|---|---|---|---|---|---|
| {{id}} | {{topic}} | {{documents}} | {{dimension}} | {{type}} | {{severity}} | {{evidence}} | {{suggestion}} |

类型取值：硬冲突 / 软不一致 / 待确认。严重度取值：高 / 中 / 低。

## 术语一致性矩阵

| 术语 | 制度A 定义/简称 | 制度B 定义/简称 | 是否一致 | 说明 |
|---|---|---|---|---|
| {{term}} | {{def_a}} | {{def_b}} | {{consistent}} | {{note}} |

## 职责主体比对矩阵

| 事项 | 制度A 归口/执行/审核 | 制度B 归口/执行/审核 | 是否一致 | 不一致类型 | 说明 |
|---|---|---|---|---|---|
| {{topic}} | {{dept_a}} | {{dept_b}} | {{consistent}} | {{type}} | {{note}} |

## 修改建议汇总

| 编号 | 对应冲突 | 建议目标 | 建议方向 | 建议内容 | 是否草案 |
|---|---|---|---|---|---|
| {{id}} | {{conflict_id}} | {{target}} | {{direction}} | {{detail}} | {{is_draft}} |

## 待确认项

| 事项 | 原因 | 涉及制度/条款位置 |
|---|---|---|
| {{topic}} | {{reason}} | {{location}} |

## 解析异常

| 异常类型 | 位置 | 说明 |
|---|---|---|
| {{type}} | {{location}} | {{detail}} |

异常类型取值：对齐低置信 / 非同体系疑义 / 格式未识别 / 其他。
