# 规则维护说明

## 1. 文件职责

| 文件 | 职责 |
|---|---|
| `scripts/audit_documents.py` | 制度分类、必备条款和章节规则的可执行数据结构 |
| `scripts/audit_normative.py` | 正文标题识别、命名规则、格式规则和自动编号识别 |
| `scripts/audit_common.py` | 共享配置、组织架构加载和组织范围识别 |
| `references/company_drafting_standard.md` | 人可读的命名、章节和格式基线 |
| `references/mandatory_clause_catalog.md` | 不同制度类型的必备条款知识库 |
| `references/organization_structure.json` | 企业组织架构机器基线 |
| `references/quick_audit_profile.md` | 默认纳入和排除范围 |
| `assets/*.md` | 下游展示可参考的报告模板 |

执行结果以脚本中的规则数据结构为准，参考文件用于解释、维护和追溯。修改规则时必须同步更新代码与参考文件，避免口径漂移。

## 2. 新增制度类型

1. 在 `references/mandatory_clause_catalog.md` 中补充规则来源、适用条件、严重程度和识别提示。
2. 在 `scripts/audit_documents.py` 中增加唯一规则编号和可遍历规则数据结构。
3. 在 `classify()` 中增加互斥、可解释的类型识别条件。
4. 在 `check_mandatory()` 和必要时的 `check_chapters()` 中选择该规则集。
5. 保证每条选中规则都返回状态、证据、严重程度和建议。
6. 使用至少一份正例和一份缺失项样例回归，检查覆盖率为 100%。

当前专门执行器覆盖员工手册、公司章程、治理机构工作细则或议事规则、采购代理机构制度；合作管理、信息化质量及其他类型暂使用通用完整性规则，并输出 `TYPE-PENDING` 提醒补充专门清单。

## 3. 修改格式规则

- 修改 `FORMAT_STANDARD` 和相应 F 规则时，同步修改 `references/company_drafting_standard.md`。
- 正文对齐和首行缩进保持排除，除非企业正式标准明确重新纳入。
- 章标题标准是黑体 16pt、加粗、居中；左右页边距标准是 3.17cm。
- 自动编号必须继续从 OOXML numbering part 和段落样式继承关系中识别。

## 4. 修改命名规则

- N1-N9 和 N11 必须使用正文正式标题。
- N10 仅比较文件名与正文标题的载体一致性。
- 新增层级词时同步更新完整性和规范性脚本的后缀列表及起草基线。
- 不得因为文件名正确而覆盖正文标题错误。

## 5. 修改组织架构

- 优先更新 `references/organization_structure.json`，不要把组织名称散落硬编码到多个脚本。
- 每个组织可配置正式名称、别名、下属单位和父级关系。
- 对省分内部部门、项目组、实验室和临时机构保持谨慎：未收录不直接判错。

## 6. 发布检查

发布或分享前执行：

```powershell
python -m py_compile scripts/audit_common.py scripts/audit_documents.py scripts/audit_normative.py scripts/quick_audit.py
python <skill-creator>/scripts/quick_validate.py .
```

还应搜索本机绝对路径、用户名、临时输出、API Key、`TODO` 和 `FIXME`，并使用真实 DOCX 验证标题识别、自动编号、覆盖率和固定输出文件。
