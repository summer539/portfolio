# 制度智能审核

## 定位

对企业制度文档执行可追溯的结构化、法规检索和符合性审核。法规数据库（`lawdb/law.db`）内置在本技能内，数据库只读使用，不自动修改法规库；法规库的维护（导入/预览/健康检查）通过本技能 `lawdb/` 子目录工具完成。

## 适配环境

- 内置法规库：`<本技能>/lawdb/law.db`（即 `skills/institution-audit/lawdb/law.db`，唯一权威副本）
- 数据表：`laws`、`articles`、`articles_fts`
- 全文检索：SQLite FTS5 `trigram`
- 制度文档解析：`scripts/parse_document.py`
- 本地法规检索：`scripts/legal_lookup.py`
- 结构校验：`scripts/validate_schema.py`
- 审核结果清单：`scripts/build_audit_list.py`（第一交付物）
- 修订清单：`scripts/build_revision_list.py`（headline/basis_human 人话版）
- 批注文本生成：`scripts/build_comment_items.py`（→ doc-revision-annotate items comment）
- 当前数据库包含法律、行政法规、部门规章、规范性文件、党内法规、香港法规；企业制度不作为国家法规依据。

## 内置法规库（lawdb/）与预览服务

法规库资产随本技能分发，位于 `<本技能>/lawdb/`：

```text
lawdb/
├── law.db                  # 唯一法规数据库（laws/articles/articles_fts）
├── preview_lawdb.py        # 静态预览生成器（→ preview.html）
├── preview.html            # 预览前端（浏览器直接打开，或由服务动态提供）
├── serve_lawdb.py          # 预览服务（Flask，动态刷新，默认 0.0.0.0:8317）
├── check_health.py         # 数据健康检查（离线）
├── verify_lawdb.py         # 官方源逐条核验（flk/规章库）
├── sync_status.py          # 按用户结构化文件同步 status
├── SOURCES.md              # 数据源说明
├── import_flk_json.py      # flk 结构化 JSON 批量入库（幂等）
├── build_lawdb.py          # docx → law.db 单部入库
├── batch_import.py         # 官方库批量导入（flk + 规章库）
├── pack_import.py          # 包清单批量导入
├── supplement_missing_body.py  # 缺失正文补充
└── search_demo.py          # FTS5 检索演示
```

预览服务启动（数据库更新后页面自动重新生成）：

```bash
cd <本技能>/lawdb && nohup python3 serve_lawdb.py --host 0.0.0.0 --port 8317 > serve_lawdb.log 2>&1 &
```

静态预览手动生成：

```bash
python3 <本技能>/lawdb/preview_lawdb.py
```

健康检查：

```bash
python3 <本技能>/lawdb/check_health.py
```

## 固定流程

```text
制度文档
↓
1. 解析文档和 Word 自动编号
↓
2. 切分章节、条、款、项和规范命题
↓
3. 判断是否需要法规检索
├─ SKIP_LEGAL_SEARCH → 原则/职责/内部管理审核
└─ SEARCH_REQUIRED → 生成检索词 → 本地法规库检索 → 候选过滤
↓
4. 形成审核结论
├─ 可以不改
├─ 必须改
└─ NEED_LIBRARY_SUPPLEMENT（本地证据不足，不能强行下法律结论）
↓
5. Grounding 和 Schema 校验
↓
6. 输出《审核结果清单.md》（第一交付物，强制）
   逐条标注：问题表现 / 法律依据 / 修改建议
↓
7. 人工确认审核结果清单（用户审阅是否合适）
↓
8. 确认后，才针对"必须改"内容生成修订清单（revision_list.json）
↓
9. 修订清单确认后，才可生成修订批注版 docx（doc-revision-annotate 技能）
   （批注文本 = headline/basis_human/suggestion 四段式人话版，由
    build_comment_items.py 生成；修订动作 old/new 按条款定位逐条构建；
    批注默认逐条不合并——修订清单怎么给，批注就怎么给）
```

**交付纪律（强制）：**

- 审核完成后**必须**先交付《审核结果清单.md》（逐条：问题表现、法律依据、修改建议），生成命令：
  ```bash
  python3 scripts/build_audit_list.py --results <audit_results.json> \
      --revision <revision_list.json> --md <审核结果清单.md> --doc-title <制度全称>
  ```
- **不得**在人工确认前交付修订清单（revision_list.json）或修订批注版 docx；修订清单只针对"必须改"内容，由人工审阅审核结果清单后决定是否生成
- 审核结果清单中"必须改"条款若拆分为多个问题点（如第八条拆 8 项），按拆分项逐项列出问题表现/法律依据/修改建议（拆分数据可来自已生成的 revision_list.json，但清单本身不交付该文件）

## 结论约束

完成审核的条款只能输出：

- `可以不改`
- `必须改`

本地法规库没有足够证据时，输出 `NEED_LIBRARY_SUPPLEMENT`，不能用模型记忆补充法规依据。

`必须改` 必须同时包含：错误类型、问题、依据条文 `article_id`、建议修改，并通过 Grounding 校验。

## 修订清单输出格式（强制）

`必须改` 条款的最终交付必须遵循 `rules/revision_output_format.md`（2026-08-27 改版为"人话版"）：

- 格式固定为三段：`【修改】`（**问题+怎么办**，不带条款位置、不带"类型X"编号）、`【修订依据】`（**人话转述**法条要义，不抄原文；法规全称+条号+（article_id）；已废止仅作背景标注）、`【修订建议】`（可直接落地的修改文本）。
- **逐项拆分，禁止合并**：同一"条"内多个独立问题必须按款/项拆成多条清单（如 `第八条第（十三）项`、`第八条第（十四）项` 各自独立），供修订技能按条款定位逐条消费。
- 本地库未收录的依据须标注"待补录"，不得冒充在库。
- 清单末尾附"依据核验说明"表（✅ 已入库 / ❌ 待补录）。

**revision_list.json 数据字段（审核员逐条撰写人话版展示字段）：**

| 字段 | 内容 | 说明 |
|---|---|---|
| `headline` | 人话版【修改】标题（问题+怎么办） | 必写；build_revision_list.py 优先输出 |
| `basis_human` | 人话版【修订依据】（法规名+条号+要义转述，**含 article_id**） | 必写；批注消费时自动去 article_id |
| `suggestion` | 可执行修改文本 | 复用结构化建议 |

**生成命令：**

```bash
# 修订清单.md（人话版四段式：【修改】/【修订依据】/【修订建议】/【修订性质】+ 依据核验表）
python3 scripts/build_revision_list.py --revision <revision_list.json> \
    --md <修订清单.md> --doc-title <制度全称>

# 批注文本（doc-revision-annotate items.json 的 comment 四段式，自动去 article_id）
python3 scripts/build_comment_items.py --revision <revision_list.json> --items <items.json>
```

## 文档解析

优先执行：

```bash
python3 scripts/parse_document.py <制度.docx> --json <结构化.json> --md <结构树.md>
```

解析器能够读取 Word `numbering.xml`，还原不在 `paragraph.text` 中的自动编号，例如：

- `第一章`、`第二章`
- `第一条`、`第二条`
- 基于 `lvlText` 的其他列表编号

**编号判读口径（强制）**：解析输出的 `label` 已含自动编号还原结果；任何"章/条缺失、无编号"类结论必须以解析输出为准，禁止拿原始 `paragraph.text` 直接判定无编号。若解析输出中 `label` 为空，须回到 `numbering.xml` 核实 `(numId, ilvl)` 模板后再下结论。

对本测试文件的预期结果：9 章、32 条，条号从第一条连续到第三十二条。

## 本地法规检索

```bash
python3 scripts/legal_lookup.py --query "软件测试" --limit 20
python3 scripts/legal_lookup.py --article-id 123
```

检索结果必须保留 `law_id`、`article_id`、法规名称、条号、正文、层级、状态和版本信息。最终报告只能引用检索返回集合中的 `article_id`。

注意：FTS5 使用 `trigram`，3 字以上走 FTS 检索；`legal_lookup.py` 已对 2 字及以下查询自动做 LIKE 兜底（全表子串匹配），两字词可直接检索。

关键词拆解、法律命题重写、正反向检索、同义词扩展、FTS5 适配、停止条件和查询日志，强制遵循：

- `rules/keyword_split_rules.md`

## 引用核验（ref_check.py）

制度条款"依照《××法》《××办法》等规定"只列名称不标文号时，用引用核验工具批量比对库内最新版本：

```bash
python3 scripts/ref_check.py <制度.docx|.txt|"直接文本"> [--json 结果.json]
```

自动完成：提取《》内法规名 → 三级名称匹配（精确 → 归一化[去掉"关于印发《》的通知"公文外壳/版本括号] → 包含兜底）→ 状态核验（现行有效/已废止/已被修改）→ 多版本取最新（按施行日期）→ 输出对比表。

结论三态：
- `现行` ✅ 库内匹配版本为现行有效（多版本时确认最新版有效）
- `过时` ⚠️ 库内最新版已废止/已被修改（如"34号令"2018版 vs 2025版同名同文号，必须看施行日期）
- `未收录` ❓ 库内无匹配（可能为企业内部制度，需人工确认；外部法规则列入"待补录"）

已知边界：包含匹配命中多个关联文件（印发通知/解释/实施办法）时归一化优先；`（试行）`版本标记保留不剥离，避免试行版与正式版误合并。

## 违规类型与分级

`必须改` 结论的错误类型标注、严重程度分级（重大/一般/轻微）及判定顺序，强制遵循：

- `rules/violation_types.md`

每个需要检索的最小规范单元必须保留实际查询日志（查询词、模式、命中数、article_id、候选淘汰理由），不得只保留建议关键词。

## 数据边界

- 当前法规库是国家及香港法规库，不含本次测试制度。
- 企业制度之间的一致性检查需要另行接入内部制度库，不能把内部制度冲突写成违反国家法律。
- 香港法规可作为本地候选依据，但应按 `香港法规` 层级和现行状态识别。
- 数据库已有多版本法规，当前审核必须优先筛选 `现行有效`；历史版本仅用于版本对照。

## 禁止事项

- 不对所有制度条款无差别检索法规。
- 不自行生成法规名称、条号或 `article_id` 作为依据。
- 不把没有本地证据包装成“可以不改”。
- 不使用“高/中/低风险”、置信度或概率替代固定结论。
- 不把内部制度要求表述为违反国家法律。
- 不自动写入、删除或覆盖 `<本技能>/lawdb/law.db`（法规库维护走 lawdb/ 子目录专用工具）。

## 输出目录建议

```text
outputs/
├── document_context.json
├── clauses.json
├── audit_results.json
└── compliance_report.md
```

规则、脚本和数据库配置分别放在本技能的 `rules/`、`scripts/`、`config/` 中，避免把确定性逻辑混进入口文件。
