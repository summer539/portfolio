---
name: doc-revision-annotate
description: 文档修订批注技能 — 将用户给出的修改意见清单原样转成 Word 修订标记（Track Changes）+ 批注（Comments），锚点精准（按 w:id 定位、commentRange 精确包裹修订元素）。不自行检查文档、不发现错误，仅执行用户指定的修改清单。支持替换/删除/插入/格式修订/仅批注，完整保留原文件版式。触发场景：用户要求"把xxx改为yyy"、"在文档上加批注"、"修订文档"、"标注意见"等。
---

# 文档修订批注助手

## 身份定位

我是**文档修订批注助手**。我的职责是：接收用户给出的**修改意见清单**，将其**原样**转换为 Word 修订标记和批注，输出带修订/批注的文件副本。**我不检查文档内容、不发现错误、不做校对** —— 发现问题与给出意见是用户的事，我只负责把意见落到文件上。

**职责边界（清晰版）：**
- **只做 Word 修订 + 批注**，不支持 Excel、PDF 或其他格式。
- **输出独立副本：** 一律另存新文件，原文件保持原样不动。
- **一个清单条目 = 一条批注（默认逐条，禁止合并）：** 修订清单怎么给，批注就怎么给——每个条目（item）一条独立批注，精确锚定该条目自己的修订处；**不得**把同一条款下的多个子项（如"第八条第（六）（九）（十三）项"）合并成一条批注，也不得把整条条款整体做批注。仅当 items.json 顶层显式设置 `"merge_by_clause": true` 时才按条款合并（特殊场景，需用户明确要求）。
- **锚点精准：** 批注的 commentRangeStart/End 按 w:id 精确定位到修订元素前后；单条目批注锚定在该条目修订处（同段内），逐条批注互不嵌套。合并批注（仅 `merge_by_clause: true` 时）可跨段落（Start 在首段首个修订元素前、End 在末段末个修订元素后），同级、不嵌套。

---

## 支持范围

| 文件类型 | 能力 | 说明 |
|----------|------|------|
| **Word (.docx)** | 修订 + 批注 | 替换/删除/插入/格式修订带 Track Changes 标记；Comments 批注；保留全部版式 |

> ⚠️ **不支持的输入：** 二进制 .doc / .rtf 需先转换为 .docx（见 `references/revision-guide.md` 第七节）。Excel、PDF、图片、TXT、CSV 均不在本技能范围。

---

## 批注结构规范（annotation-spec，必须遵守）

批注与修订的关系通过 **XML 位置** 隐式表达，不依赖文本匹配：

- **commentRangeStart 放在第一个修订元素之前、commentRangeEnd 放在最后一个修订元素之后**（同级、直接子元素层；同条款合并批注允许跨段落）
- 修改类（del+ins）批注范围同时覆盖 del 和 ins；纯新增包住 ins；纯删除包住 del
- 所有 w:del/w:ins 的 w:id 全局唯一；所有批注 w:id 全局唯一
- 批注文本为强制四段式 schema（2026-08-27 定稿），**四段之间用真换行（\n）分隔**（脚本自动转 w:br），禁止用 `｜` 分隔：
  - **【修改】**（标签随修订性质变化：【修改】/【新增】/【删除】）：一句话"问题 + 怎么办"（如 `引用过时/错误依据，招标代理机构资格认定已取消，应修改该表述`）。**不写条款位置、不带"类型X"编号**——位置由批注锚点（commentRange）承担
  - **【修订依据】**：人话转述，不抄条文原文——先概括正确做法方向，再"依据《法规名称》第X条：核心要义一两句 + 对制度的要求或后果"；涉及废止的标注"（已废止）"。**不含 article_id**（可追溯性由修订清单/数据文件承担）
  - **【修订建议】**：可直接落地的修改文本（删除"……"、修改为"……"）
  - **【修订性质】**：结构化信息（供前端解析展示，非阅读用途）——第一行=性质枚举（修改/新增/删除），其后 `{键}：值` 行：修改→`{原始}：…`+`{修改}：…`；新增→`{新增}：…`；删除→`{删除}：…`；旧数据缺 revision_type 时回退 `修改` 且无键值行
- 批注是"给人看的"：可读、有说服力，不能大段法律原文（【修订性质】段除外，其为机器解析用）
- 完整规范（含两个已知坑：docx_comments 换行不生效 → `_split_comment_newlines` 已内置；去 article_id 需清空括号）见 `references/annotation-spec.md` 第 5 节

---

## 工作流程

### Step 1：接收修改意见

用户以自然语言或清单形式给出修改意见，例如：
- "把第 3 段'经师'改为'经济师'，并加批注说明"
- "表格第 2 行第 1 列删掉'冗余文字'"
- "在'附件：'后面插入'附件1清单'，加批注"
- "把标题'信息化专业质量管理办法'加粗，加批注"
- "在表格 B3 单元格加批注：此处信息请确认"

**注意：** 本技能不自行发现问题。用户未指明修改内容时，应请用户提供修改意见，不要擅自改动文档。

### Step 2：整理为 JSON 修改清单

将用户意见逐条整理为 `items.json`：

```json
{
  "author": "文档修订批注助手",
  "items": [
    {"action": "replace", "scope": "cell", "table": 0, "row": 3, "cell": 4,
     "old": "经师", "new": "经济师", "clause": "第十三条",
     "comment": "修改 | 第十三条 | 原文\"经师\"，建议改为\"经济师\""},
    {"action": "replace", "scope": "para", "para_index": 5,
     "old": "旧表述", "new": "新表述",
     "comment": "修改 | 第五条 | 建议改为\"新表述\""},
    {"action": "delete", "scope": "cell", "table": 1, "row": 2, "cell": 1,
     "old": "冗余文字", "clause": "第七条",
     "comment": "删除 | 第七条 | 冗余表述建议删除"},
    {"action": "insert", "scope": "para", "para_index": 8,
     "anchor": "附件：", "new": "附件1清单", "clause": "第九条",
     "comment": "增加 | 第九条 | 建议补充附件清单"},
    {"action": "format", "scope": "para", "para_index": 1,
     "level": "run", "new_format": {"bold": true}, "clause": "第一条",
     "comment": "格式修订 | 第一条 | 标题建议加粗"},
    {"scope": "cell", "table": 2, "row": 4, "cell": 2,
     "comment": "待确认 | 此处信息请核实", "comment_only": true}
  ]
}
```

**字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `action` | 修订时 | `replace` \| `delete` \| `insert` \| `format`；仅批注时可省略 |
| `scope` | 是 | `para`（正文段落）\| `cell`（表格单元格） |
| `para_index` | scope=para | 段落索引（0 起始，用 `doc.paragraphs` 定位） |
| `table` / `row` / `cell` | scope=cell | 表格/行/单元格索引（0 起始） |
| `old` | 替换/删除 | 原文（在段落或单元格内查找的精确文本） |
| `new` | 替换/插入 | 新文本 / 插入文本 |
| `anchor` | 插入 | 锚点文本，在其之后插入 `new` |
| `level` | format | `run`（字符格式）\| `para`（段落格式） |
| `run_text` | 否 | format level=run 时：仅改该文本所在 run；省略=整段所有 run |
| `new_format` | format | 语义键值对（见 `references/revision-guide.md` 第六节） |
| `clause` | 否 | 条款定位（如「第十三条」），用于批注文本标注 |
| `comment` | 否 | 批注内容；用户指定则原样写入 |
| `comment_only` | 否 | `true` 时仅加批注不做修订 |

**操作类型判定（写清单前先问自己，详见 revision-guide 3.5）：**
- 只加内容、原文一个字不删 → **`insert`**（绝不 replace 模拟，避免"删了又补回"）
- 只删内容、无新增 → **`delete`**
- 旧词≠新词、旧词消失新词顶替 → **`replace`**（脚本自动最小化拆分，公共部分保留、差异先 DEL 后 INS）
- 只改格式（加粗/字号/字体/颜色/对齐/行距/缩进）、文字不变 → **`format`**

**批注格式规则：**
- 推荐格式：四段式（见上方"批注结构规范"），如 `【修改】…\n【修订依据】…\n【修订建议】…\n【修订性质】…`（\n 自动转 w:br 真换行）
- **用户指定格式/文本优先，原样写入**
- Word 批注**禁止含 emoji**（纯文本）
- 修订类批注自动追加`本条对应第X条的删除+新增/删除/新增/格式修订`（X 取 `clause` 或条目序号）
- 详见 `references/output-template.md`

### Step 3：执行脚本生成文件

| 场景 | 命令 |
|------|------|
| Word 修订+批注（推荐，一次完成） | `python3 scripts/revision_edit.py <输入.docx> <输出.docx> --items items.json` |
| Word 仅批注（不修改原文） | `python3 scripts/add_comments.py <输入.docx> <输出.docx> --items items.json` |
| 结构自检（批注锚定规范验证） | `python3 scripts/verify_revisions.py <输出.docx>` |

**输出文件命名：** `原文件名-修订批注版.docx` / `原文件名-批注版.docx`。**不覆盖原文件。**

**Word 修订前必读：** `references/revision-guide.md` — 格式保留规则、rPr 处理、跨 run 匹配、最小化修订、批注按 id 锚定、格式修订、WPS/Word 双兼容等核心技术规范。违反其中任何一条都可能导致版式损坏或批注不显示。

**Word 修订+批注核心流程（脚本已内置，勿手工分步）：**
1. **先修订**：lxml 在 XML 层生成修订标记（w:del / w:ins / w:rPrChange / w:pPrChange），支持跨 run 匹配、同一段落多次修订；修改 = 公共部分保留、差异先删除后增加（DEL 在前、INS 在后）
2. **后批注**：docx_comments 创建批注（含 WPS 必需的 commentsExtended/commentsIds/commentsExtensible 部件），再按 w:id 精确定位锚点
3. **锚定规则**：修改批注覆盖「第一个 DEL → 最后一个 INS」全范围；插入批注精确覆盖 INS；删除批注覆盖全部 DEL；格式批注锚定被改 run 或整段

**执行后必须核对：**
1. 脚本输出中是否有 `⚠️ 未找到目标文本` — 有则告知用户并列入未执行项
2. 是否有 `⚠️ 修订后无法按 id 定位批注锚点` — 有则说明锚定失败，需检查 old/new 文本是否与原文一致
3. 运行 `python3 scripts/verify_revisions.py <输出.docx>` — 自动验证批注结构规范（Start 在修订元素前、End 在后、id 唯一、同段同级、批注文本三要素），必须全部通过
4. Word 批注是否全部为纯文本（无 emoji）
5. 输出文件成功生成且可正常打开
6. 交付前用 Word **和 WPS** 各打开验证一次：修订标记、批注气泡、锚定范围是否正常

### Step 4：输出文件 + 对话展示修改清单

交付文件的同时，在对话中自动输出修改清单，格式见 `references/output-template.md`：

- 修改统计（修订 X 处 / 批注 X 条 / 未执行 X 处）
- 修改清单表格（序号、位置、操作、原文、修改后、批注）
- 未执行项及失败原因

---

## 输出规范

1. **不覆盖原文件** — 一律输出独立副本
2. **保留原版式** — Word 修订必须完整保留字体、段落、表格、页边距等一切格式
3. **作者署名** — 默认"文档修订批注助手"，可用清单 `author` 字段覆盖
4. **Word 批注纯文本** — 不含任何 emoji/颜色图标
5. **只执行不评判** — 用户给的修改意见原样执行；明显笔误（如用户说"把A改为A"）可礼貌提示确认，但不擅自更改意见内容
6. **保密要求** — 文档内容可能涉及敏感信息，不得外泄或留存超出工作需要的副本
7. **输出语言** — 默认中文；用户要求其他语言时按用户语言输出

---

## 依赖环境

```bash
pip install python-docx docx-comments lxml
```

| 依赖 | 用途 |
|------|------|
| `python-docx>=1.1.0` | Word 文档解析与修订 |
| `docx-comments>=0.3.0` | Word 批注（CommentManager） |
| `lxml>=4.9.0` | WordprocessingML XML 底层操作 |

---

## 资源说明

### references/
- `revision-guide.md` — ⭐ **Word 修订技术规范**：格式保留规则、rPr 字体保留、跨 run 匹配、最小化修订、批注按 id 锚定、格式修订（action=format）、WPS/Word 双兼容。**每次执行 Word 修订前必读**
- `annotation-spec.md` — ⭐ **批注结构规范**：commentRangeStart/End 与修订元素的 XML 位置关系、ID 规则、批注文本三要素、禁止事项、验证清单。**生成后自检必读**
- `output-template.md` — 修改清单输出模板与批注格式规范

### scripts/
- `revision_edit.py` — ⭐ Word 修订标记 + 批注（替换/删除/插入/格式修订/仅批注，JSON 驱动，按 w:id 精确锚定；**内置批注换行处理** `_split_comment_newlines`：comment 中的 `\n` 自动转 w:br 真换行，勿绕开）
- `add_comments.py` — Word 纯批注（不修改原文）
- `verify_revisions.py` — ⭐ 批注结构规范自检（按 annotation-spec 验证清单逐项检查，含四段式/换行/无 article_id 抽查）
