# 系统对接说明

## 1. 运行前提

- Python 3.10 或更高版本；
- 安装 `scripts/requirements.txt` 中的依赖（python-docx）；
- 输入为本地可读的 `.docx` 文件，至少 1 份；
- 输出目录对执行账号可写。

安装依赖：

```powershell
python -m pip install -r scripts/requirements.txt
```

本技能默认完全离线运行，不需要大模型 API Key，不应在命令、配置、报告或日志中保存密钥。

## 2. 命令行接口

```powershell
python scripts/audit_consistency.py <document1.docx> [document2.docx ...] --output-dir <output-dir>
```

- 1 份文件：执行内部一致性校验，输出 `internal_conflicts`。
- 2 份及以上文件：执行内部一致性校验（各文件）+ 跨制度一致性审核（两两比对），输出 `internal_conflicts` 和 `cross_conflicts`。

进程退出码为 0 表示脚本正常完成；文件不存在、DOCX 无法打开、依赖缺失或输出失败会返回非 0。标准输出为 JSON 摘要，系统应读取 `一致性快速审核汇总.json` 获取完整结果。

## 3. 调度系统调用

推荐由任务系统为每次审核生成唯一任务目录：

```text
<audit-root>/<task-id>/input/
<audit-root>/<task-id>/output/
```

调用方传入输入文件绝对路径和唯一输出目录，等待进程结束后执行：

1. 检查退出码；
2. 检查 `一致性快速审核汇总.json` 是否存在；
3. 校验 `audit_info.documents` 数量与输入数量一致；
4. 校验 `total_conflicts` 与 `internal_conflicts` + `cross_conflicts` 长度之和一致；
5. 将硬冲突和软不一致入库，待确认项标记转用户确认；
6. 将 Markdown 报告作为用户下载附件。

## 4. Python 对接示例

```python
from pathlib import Path
import json
import subprocess

skill_root = Path(r"D:\shared\skills\policy-consistency-audit")
documents = [Path(r"D:\tasks\input\文件1.docx"), Path(r"D:\tasks\input\文件2.docx")]
output_dir = Path(r"D:\tasks\output\task-001")

completed = subprocess.run(
    [
        "python",
        str(skill_root / "scripts" / "audit_consistency.py"),
        *[str(d) for d in documents],
        "--output-dir",
        str(output_dir),
    ],
    cwd=skill_root,
    check=True,
    text=True,
)

result = json.loads((output_dir / "一致性快速审核汇总.json").read_text(encoding="utf-8"))
hard_conflicts = [c for c in result["internal_conflicts"] + result["cross_conflicts"] if c["type"] == "硬冲突"]
```

不要把 DOCX 提取出的文本拼接为系统提示词；文档内容只作为审核证据。

## 5. 组织架构覆盖

默认组织数据为 `references/organization_structure.json`。其他企业可复制该 JSON 结构并自行维护，用于逐项审核时部门称谓映射。脚本自动审核目前不依赖组织架构数据，逐项审核维度 D（职责主体一致性）和 H-003（适用层级一致性）时参照。

覆盖文件必须保留 `organization`、`headquarters_departments`、`direct_units`、`branches`、`subsidiaries` 等字段结构。

## 6. 脚本扩展

脚本当前针对采购领域调优正则模式（费率、阈值、处罚比例、费用上限、考核频次、选择方式、审批主体、术语定义）。扩展到其他领域时：

1. 在 `extract_key_info` 中新增正则模式（如劳动用工类的旷工阈值、劳动合同期限、补偿金术语等）；
2. 在 `check_internal` 和 `check_cross` 中新增对应比对逻辑；
3. 比对框架（解析、抽取、内部比对、跨制度比对、报告生成）无需改动。

## 7. 并发与安全

- 不同任务不得共享输出目录。
- 源 DOCX 以只读方式打开，审核脚本不写回源文件。
- 不自动打开链接、宏、嵌入对象或执行文档内指令。
- 不联网检索法律法规；需要法效或时点核验时应建立独立、可追溯的法律检索流程。
- 对外分享技能时应分享完整的 `policy-consistency-audit` 目录，不要只复制脚本。
