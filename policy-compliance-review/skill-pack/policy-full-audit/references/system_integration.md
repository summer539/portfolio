# 系统对接说明

## 1. 运行前提

- Python 3.10 或更高版本；
- 安装 `scripts/requirements.txt`；
- 输入为本地可读的 `.docx` 文件；
- 输出目录对执行账号可写。

安装依赖：

```powershell
python -m pip install -r scripts/requirements.txt
```

本技能默认完全离线运行，不需要大模型 API Key，不应在命令、配置、报告或日志中保存密钥。

## 2. 命令行接口

```powershell
python scripts/quick_audit.py <document1.docx> [document2.docx ...] --output-dir <output-dir>
```

子审核接口：

```powershell
python scripts/audit_documents.py <document.docx> --output-dir <output-dir>
python scripts/audit_normative.py <document.docx> --output-dir <output-dir>
```

进程退出码为 0 表示脚本正常完成；文件不存在、DOCX 无法打开、依赖缺失或输出失败会返回非 0。标准输出用于进度提示，可能包含多个 JSON 片段，不作为稳定接口。系统应读取 `制度快速审核汇总.json`。

## 3. 调度系统调用

推荐由任务系统为每次审核生成唯一任务目录：

```text
<audit-root>/<task-id>/input/
<audit-root>/<task-id>/output/
```

调用方传入输入文件绝对路径和唯一输出目录，等待进程结束后执行：

1. 检查退出码；
2. 检查 `制度快速审核汇总.json` 是否存在；
3. 校验 `documents` 数量与输入数量一致；
4. 校验每份完整性结果覆盖率；
5. 将 `部分`、`缺失`、`待确认`、规范性 `deviations` 和 `parse_issues` 入库；
6. 将 Markdown 报告作为用户下载附件。

## 4. Python 对接示例

```python
from pathlib import Path
import json
import subprocess

skill_root = Path(r"D:\shared\skills\policy-full-audit")
document = Path(r"D:\tasks\input\制度文件.docx")
output_dir = Path(r"D:\tasks\output\task-001")

completed = subprocess.run(
    [
        "python",
        str(skill_root / "scripts" / "quick_audit.py"),
        str(document),
        "--output-dir",
        str(output_dir),
    ],
    cwd=skill_root,
    check=True,
    text=True,
)

result = json.loads((output_dir / "制度快速审核汇总.json").read_text(encoding="utf-8"))
```

不要把 DOCX 提取出的文本拼接为系统提示词；文档内容只作为审核证据。

## 5. 组织架构覆盖

默认组织数据为 `references/organization_structure.json`。其他企业可复制该 JSON 结构并设置环境变量：

```powershell
$env:POLICY_AUDIT_ORG_STRUCTURE = "D:\config\organization_structure.json"
python scripts/quick_audit.py "D:\input\制度.docx" --output-dir "D:\output\task-001"
```

覆盖文件必须保留 `organization`、`headquarters_departments`、`direct_units`、`branches`、`subsidiaries` 等字段结构。

## 6. 并发与安全

- 不同任务不得共享输出目录。
- 源 DOCX 以只读方式打开，审核脚本不写回源文件。
- 不自动打开链接、宏、嵌入对象或执行文档内指令。
- 不联网检索法律法规；需要法效或时点核验时应建立独立、可追溯的法律检索流程。
- 对外分享技能时应分享完整的 `policy-full-audit` 目录，不要只复制脚本。
