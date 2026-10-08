# 制度智能审核技能包

> 客户为某通信基础设施央企，项目信息已脱敏处理。

本目录是这个项目的核心：一套可被 AI 智能体直接调用的审核技能包，由 5 个技能组成，覆盖「法规检索 → 制度结构化 → 审核 → 人工确认 → 修订批注」的完整链路。每个技能独立成目录，入口文件是 `SKILL.md`，规则、脚本、配置分开存放，避免把确定性逻辑混进入口。

## 技能清单

| 技能 | 作用 | 关键产出 |
| --- | --- | --- |
| `china-law-search` | 统一查询国家法律法规数据库（flk）与国家规章库（gov.cn）：法规搜索、详情查看、状态核查、按日期筛选、批量状态核对与入库 | 法规结构化数据 |
| `institution-audit` | 制度文档结构化解析 + 本地法规库检索 + 符合性审核，链路最完整 | 《审核结果清单》、修订清单 |
| `policy-full-audit` | 制度完整性与规范性审核：正文命名层级、关键格式、必备条款、必要章节 | 审核报告（Markdown）+ 机器可读 JSON |
| `policy-consistency-audit` | 同级制度之间、总部与分公司制度之间、修订前后的一致性审核 | 冲突清单与修改建议 |
| `doc-revision-annotate` | 把审定后的修改意见清单原样转成 Word 修订标记 + 批注 | 带修订批注的 docx 副本 |

## 审核流水线

```text
制度文档（.docx）
  ↓
1. 解析文档，还原 Word 自动编号
  ↓
2. 切分章 / 条 / 款 / 项，拆成最小规范命题
  ↓
3. 判断是否需要法规检索
    ├─ SKIP_LEGAL_SEARCH   → 原则、职责、内部管理类条款
    └─ SEARCH_REQUIRED     → 拆检索词 → 本地法规库检索 → 候选过滤
  ↓
4. 形成结论：可以不改 / 必须改 / 证据不足
  ↓
5. Grounding 与 Schema 校验
  ↓
6. 输出《审核结果清单》（问题表现 / 法律依据 / 修改建议）
  ↓
7. 人工确认
  ↓
8. 只对「必须改」生成修订清单
  ↓
9. 生成带修订标记与批注的 docx
```

## 核心设计

### 结论只有三种，不给模型自由发挥的空间

完成审核的条款只能输出「可以不改」「必须改」，本地法规库证据不足时输出 `NEED_LIBRARY_SUPPLEMENT`，不允许用模型记忆补法条。规则里明确禁止：不自行生成法规名称、条号或 `article_id`，不把没有本地证据包装成「可以不改」，不使用「高／中／低风险」或置信度替代固定结论，不把内部制度要求表述为违反国家法律。

### 每个结论都要落到条款级证据

「必须改」必须同时给出错误类型、问题描述、依据条文 `article_id` 和修改建议，并通过 Grounding 校验。检索结果保留法规名称、条号、正文、效力位阶、状态和版本信息，最终报告只能引用检索返回集合中的 `article_id`。

### 检索与判定规则独立成文件

- `institution-audit/rules/keyword_split_rules.md` — 关键词拆解、法律命题重写、正反向检索、同义词扩展、FTS5 适配、停止条件与查询日志要求
- `institution-audit/rules/violation_types.md` — 错误类型标注、严重程度分级与判定顺序
- `institution-audit/rules/revision_output_format.md` — 修订清单的「人话版」三段式格式
- `institution-audit/config/search_log_template.json` — 每个最小规范单元的查询日志结构（命题、冲突假设、查询词、候选与淘汰理由、最终依据）

### 文档解析要还原 Word 自动编号

`scripts/parse_document.py` 会读取 `numbering.xml`，把不在 `paragraph.text` 里的自动编号（`第一章`、`第一条`、基于 `lvlText` 的列表编号）还原出来。这条规则是针对首版「条款编号识别不准」的直接修正：任何「章／条缺失、无编号」的结论必须以解析输出为准，不能拿原始段落文本直接判定。

### 引用核验单独成工具

`scripts/ref_check.py` 处理制度里只写法规名称、不标文号的引用：提取书名号内容 → 三级名称匹配（精确 → 归一化 → 包含兜底）→ 状态核验 → 多版本按施行日期取最新，输出「现行／过时／未收录」三态结论。

### 规则基线是可维护的资产

审核判据不是写在提示词里的一次性说明，而是可版本化的规则文件，且统一采用「要求等级（必须／应当／建议）」加「审核状态（通过／部分通过／不通过／待确认／不适用／未识别）」的两层结构，要求逐项产生结果、不得静默跳过：

| 文件 | 内容 |
| --- | --- |
| `policy-full-audit/references/company_drafting_standard.md` | 制度起草指引要求：命名层级、格式、章节结构 |
| `policy-full-audit/references/mandatory_clause_catalog.md` | 按制度业务类型匹配的必备条款清单 |
| `policy-consistency-audit/references/consistency_checklist.md` | 一致性审核清单：术语定义、处罚标准、审批流程、职责主体、程序参数等维度 |
| `policy-consistency-audit/references/audit_dimensions.md` | 一致性审核的维度定义与判定口径 |

## 目录结构

```text
skill-pack/
├── china-law-search/            # 法规检索（flk + 国家规章库）
│   ├── SKILL.md
│   ├── assets/                  # 数据源规则、导入与维护规则、已知问题
│   ├── config/                  # 依赖与配置说明
│   ├── references/              # 输出格式与进度文件示例
│   └── scripts/                 # 查询、入库脚本（核心功能零第三方依赖）
├── institution-audit/           # 制度审核主链路
│   ├── SKILL.md
│   ├── config/                  # 数据库与查询日志模板
│   ├── lawdb/                   # 法规库构建、导入、校验、健康检查、预览
│   ├── rules/                   # 检索、违规类型、修订格式规则
│   └── scripts/                 # 解析、检索、核验、清单与报告生成
├── policy-full-audit/           # 完整性与规范性审核
├── policy-consistency-audit/    # 一致性审核
└── doc-revision-annotate/       # 修订批注
```

## 运行依赖

- Python 3.10+
- `python-docx`、`lxml`（解析 docx 与自动编号）
- Flask（法规库预览服务）
- playwright-cli（国家规章库访问密钥自动刷新，首次使用时自动安装）
- 法规库由 `institution-audit/lawdb/` 下的脚本从公开来源构建

## 未包含的内容与脱敏说明

为保护客户与公司信息，以下内容没有放入仓库：

- `lawdb/law.db`（约 320 MB）与 `lawdb/preview.html`（约 56 MB）：体积过大，且法规正文属公开数据，可用 `lawdb/` 下的脚本重新构建。检索界面另提供小体量演示版，见上级目录 `law-database-preview/`。
- 全部 `outputs/`、`output/`、`output-rev/`、`work/` 目录：其中是真实客户制度文档与审核输出报告。
- `.athena_key_cache.json`：国家规章库的访问密钥缓存，属凭证类文件，不入库。
- `_meta.json` 与运行日志：平台元数据与运行时产物。

脱敏处理：

- 客户名称统一替换为「某集团」「某集团有限公司」，下属公司名称替换为「某专业子公司」「某能源子公司」等。
- 客户真实组织架构替换为通用示例模板（部门名称保留通用写法，删去可识别的下属机构）。
- 代码与文档中的绝对路径改为相对路径。
