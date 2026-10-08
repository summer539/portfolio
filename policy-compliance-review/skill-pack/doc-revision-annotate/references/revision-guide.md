# Word 修订与批注技术规范

> 本文档是 doc-revision-annotate 的技术核心。执行任何 Word 修订/批注操作前必须阅读并遵守。
> 这些规则来自大量实战经验，违反任何一条都可能导致版式损坏或修订显示异常。

---

## 一、格式保留规则（最高优先级）

目标是"仅修订/仅批注，版式完全一致"：

- **禁止修改纸张方向/尺寸** — 原稿是 Letter 纵向就不能改成 A4 横向
- **禁止修改页边距**
- **禁止修改表格列宽** — 从源文件读取精确列宽（docx 用 `w:tblGrid/w:gridCol` 的 `w:w`）
- **禁止添加分页符、cantSplit 等结构性标记**
- **禁止修改表格属性**（tblW、tblLayout、table indent）
- **禁止修改段落属性**（w:pPr）— 不得改动对齐方式、行距、缩进、段前段后间距、大纲级别等（`action=format` 的段落格式修订除外，见第六节）
- **禁止删除或整体替换段落** — 所有修订操作必须在 run 级别进行，不能 replace 整个段落 XML 或清空段落再重写
- **禁止在修订过程中增加多余空白/空行/换行符**
- **保留原文所有 run 的字体属性** — 包括字体名称（ascii/hAnsi/eastAsia）、字号（sz/szCs）、加粗、斜体、颜色、下划线等；del 和 ins 元素内的 rPr 必须完整复制原 run 的 rPr
- **标题/Heading 样式的段落** — 修订时不得改变其样式（style），仅在其 run 内做 del+ins 操作

---

## 二、修订标记字体保留（最严格要求）

- **核心原则：** 原 run 有什么 rPr，del/ins 的 run 就有什么 rPr；原 run 没有 rPr，del/ins 的 run 也绝不能有 rPr
- 创建 w:del 和 w:ins 时，新 run 的 rPr 必须 **复制原始 run 的完整 rPr**（含 rFonts、sz、szCs 等）
- 在复制后的 rPr 上**追加** `w:rStyle w:val="Del"` 或 `w:rStyle w:val="Ins"`
- **❌ 绝对禁止：** 在原始 run 没有 rPr 的情况下，凭空创建一个仅含 rStyle 的 rPr。这会覆盖段落/主题继承的默认字体设置，导致修订文本显示为等线/宋体以外的默认字体
- ✅ 正确做法：原 run 无 rPr → del/ins 的 run 也不加 rPr。Word 会依据 w:del/w:ins 元素类型自动渲染删除线和下划线
- 脚本中 `_add_tracked_style()` 已封装此逻辑（原无 rPr 时返回 None 而非空 rPr）

---

## 三、跨 run 文本匹配与修订（关键，建议反复阅读）

在同一个段落上做多次 del+ins 替换时，位置追踪非常容易出错。以下为经过实战验证的正确做法：

### 3.1 核心卡点：w:br 元素

Word 文档中的换行可能来自 `w:br` 元素（而非 `\n` 字符）。`get_run_text()` 必须像 python-docx 的 `run.text` 一样，将 `w:br` 转换为 `\n`，将 `w:tab` 转换为 `\t`：

```python
def get_run_text(run_elem):
    texts = []
    for child in run_elem:
        tag_local = child.tag.split('}')[-1]
        if tag_local == 't':
            if child.text:
                texts.append(child.text)
        elif tag_local == 'br':
            texts.append('\n')
        elif tag_local == 'tab':
            texts.append('\t')
    return ''.join(texts)
```

**不得**使用 `findall('w:t')` + `findall('w:delText')`，这会将 `w:br` 丢失且混入 delText。

### 3.2 核心卡点：只追踪直接 w:r 子元素

`para.text` (python-docx) 只返回**段落直接子元素**中的 `w:r` 文本，**不包含** `w:del` 和 `w:ins` 内部的 run。但 `p_elem.findall('w:r')` 会递归查找，把 del/ins 内部的 run 也找出来。

**❌ 错：** `runs = list(p_elem.findall(f'{{{W}}}r'))` ← 递归查找，多出 del/ins 内部的 run

**✅ 对：** `direct_runs = [child for child in p_elem if child.tag == f'{{{W}}}r']` ← 只取直接子元素

### 3.3 跨 run 匹配（替换文本可能横跨多个 run）

**❌ 旧方案的致命 bug：** 只处理"old_text 落在单个 run 内"的情况。WPS 文档的 run 常被 rPr 属性差异（hint/eastAsia/lang 等）拆碎，如 `"2026年5月"` 可能是 `run("  |  2026年") + run("5") + run("月")` 三个 run。旧逻辑只匹配第一个 run 内的部分，导致替换不完整。且多次修订后段落里已有 del/ins 元素，旧的位置追踪随之失效。

**✅ 正确做法：** 全量收集容器 → 拼接全文 → 定位匹配区间 → 重建段落：

```python
def collect_containers(p_elem):
    """收集参与文本匹配的容器：直接子元素 w:r 与 w:ins（视为修订后已接受）。
    返回 (containers, full_text)；w:del 不算（已删除文本不可作匹配源）。"""
    containers, parts = [], []
    for child in p_elem:
        tag = local_name(child.tag)
        if tag == 'r':
            t = get_run_text(child)
            containers.append((child, t, False)); parts.append(t)
        elif tag == 'ins':
            t = get_ins_text(child)
            containers.append((child, t, True)); parts.append(t)
    return containers, ''.join(parts)
```

1. `full_text = ''.join(各容器文本)`，在其中 `index(old_text)` 得到 `[start, end)`
2. 遍历 `p_elem` 所有直接子元素：非容器元素（pPr/commentRange/bookmark 等）直接 `deepcopy` 保留；容器按匹配区间切分为 before / match / after
3. match 部分按 `plan_replace(old_text, new_text)` 的最小化方案生成 `w:del` / `w:ins`：**新旧文本公共部分保留（不删不加），差异部分先 DEL 后 INS**（用户强制规则，见 3.5）
4. 清空段落，按序 append 重建

**多次修订同一段落的注意点：** 第二次替换时段落里已有第一次的 del/ins。`collect_containers` 把 `w:ins` 也视为容器（其文本参与匹配，相当于"接受修订后的文本"），`w:del` 不参与。这样第二次的 old_text 可以命中第一次插入的内容；若 old_text 恰好包含第一次的 INS 文本，则 INS 的 match 部分会转为 DEL（删除先前插入的内容）。

### 3.4 批注锚定必须按修订 id 重新定位（元素引用会失效，文本定位也不可靠）

**❌ 致命 bug 1：** 阶段 1 修订时保存 DEL/INS 元素的引用，阶段 2 加批注时直接使用。但**同一段落被第二次修订时，段落重建会把第一次的 DEL/INS deepcopy 一份**，旧引用指向的元素已不在段落中，`index()` 直接报错。

**❌ 致命 bug 2（最小化拆分后）：** 修订阶段只保存文本信息 `(para, old_text, new_text)`，批注阶段按文本内容查找——replace 启用最小化拆分后，**DEL 的拼接文本 ≠ old_text**（公共部分不删），`_del_range` 无法定位；INS 也可能被拆成多个片段，`_find_ins` 按整段 new_text 匹配不到。

**✅ 正确做法：** 修订阶段记录本次修订生成的**全部 DEL/INS 的 w:id**；批注阶段按 id 在最终段落结构中查找元素（w:id 是 XML 属性，deepcopy 重建后保留，唯一且稳定）：

- `resolve_anchor_by_ids(p_elem, del_ids, ins_ids)`：有 INS → 第一个 DEL（无 DEL 则第一个 INS）到最后一个 INS；无 INS（纯删除）→ 第一个 DEL 到最后一个 DEL

锚定规则（用户要求，2026-08-26 固化）：
- **修改 replace**：范围 = 第一个 DEL 前 → 最后一个 INS 后（覆盖被删原文 + 新增文本全范围）
- **增加 insert**：范围 = INS 前 → INS 后（精确覆盖插入内容）
- **删除 delete**：范围 = 第一个 DEL 前 → 最后一个 DEL 后（定位在删除位置）
- **位置铁律**：commentRangeStart 在第一个修订元素之前、commentRangeEnd 在最后一个修订元素之后，同级（直接子元素层）；单处批注同段落，同条款合并批注允许跨段落（Start 段在 End 段之前）
- **批注文本**：修订类批注自动追加「本条对应第X条的删除+新增」（修改类）/「…的删除」（纯删除）/「…的新增」（纯插入）/「…的格式修订」（format），X 优先取 item.clause/条款号，否则为条目序号

### 3.5 修订精度规范（增加 / 删除 / 修改[内容+格式]，最小化修订，强制）

用户明确要求：修订必须精准，按三种类型执行，**禁止出现「多删除又补回来」的情况**（DEL 的 old 与 INS 的 new 含大量公共文本，导致原文被删掉又原样补回，视觉极乱）。其中「修改」分**内容修改**（改文字）与**格式修改**（改格式、不动文字）两类，格式修改走 `action=format`（见第六节），机制与内容修改完全不同（`w:rPrChange`/`w:pPrChange`，而非 `w:del`/`w:ins`）。

**三类操作与正确用法：**

| 类型 | 语义 | 正确做法 | 错误做法 |
|------|------|----------|----------|
| 增加 | 新增内容，不改原文 | `insert`（anchor 后插入 new） | 用 `replace` 模拟（old=某句，new=某句+新内容），导致原句被删又补回 |
| 删除 | 删除内容，不新增 | `delete`（仅 DEL） | 用 `replace` 模拟（old=某句，new=""）虽等价但应直接用 delete |
| 修改（内容·整句） | 整句话要改 | `replace`：脚本自动最小化拆分，公共部分保留、差异先 DEL 后 INS | 手工把 old/new 扩到整句（脚本仍会最小化，但清单应尽量只含差异） |
| 修改（内容·词） | 仅某词要改 | `replace`：DEL 该词 + INS 正确词 | old/new 扩到整句，把未变的上下文也标进修订 |
| 修改（格式·字符） | 仅改字符格式，不动文字 | `format`：level=run + new_format | 用 `replace` 删原文改文字（把格式问题当内容改） |
| 修改（格式·段落） | 仅改段落格式 | `format`：level=para + new_format | 用 `replace` 删原文改文字 |

**核心判定（写清单前先问自己）：**
- 原文一个字都不需要删、只加内容 → 用 `insert`，**绝不**用 `replace`。
- 需要把「A」改成「AB」这类「在词前/后加前缀后缀」的修改，本质是「增加」，用 `insert`（在锚点后插 B，或在 A 前插 B），而不是 `replace("A", "AB")` 导致 A 被删又补回。
- 只有真正「旧词 ≠ 新词」、旧词要消失、新词要顶替时，才用 `replace`，且 old/new 尽量只含差异部分。
- 只改格式（加粗/字号/字体/颜色/对齐/行距/缩进等）、文字不变 → 用 `format`，**绝不**用 `replace`。

**replace 自动最小化拆分（2026-08-25 用户强制规则，脚本已内置）：**
即使清单里给了整句 old/new，脚本也会自动识别新旧文本的公共部分（最长公共子串，≥2 字符），公共部分**保留不删不加**，只对差异部分生成「先 DEL 后 INS」。效果示例：

| old | new | 脚本生成 |
|-----|-----|----------|
| 报告；；； | 报告； | `DEL("；；")`（无 INS，不再"删报告又加报告"） |
| 第十四条 第十四条廉洁工作要求 | 第十四条 廉洁工作要求 | `DEL("第十四条")`（重复条号只删一次） |
| 按照相关程序确定采购代理机构名单， | 按照公开透明的程序确定采购代理机构名单（名单向所有符合条件的登记代理机构开放）， | `DEL("相关")` + `INS("公开透明的")`，保留"程序确定采购代理机构名单"；`DEL("，")` + `INS("（名单向所有符合条件的登记代理机构开放），")` |

- 公共块最短保留 2 字符（`MIN_COMMON_LEN`），单字符公共（如"，""的"）并入差异，避免修订碎片化。
- 无任何公共块时才表现为整段 DEL + INS。
- 超长文本（m×n > 4,000,000）自动降级为公共前后缀拆分，保证性能。
- 递归锚定公共子串的**最左出现**，避免重复文本（如条号重复出现）选错保留位置。

**典型反例（禁止）：**
```json
// ❌ 错误：old 是 new 的前缀，导致「采购代理服务费。」被删又原样补回
{"action": "replace", "old": "采购代理服务费。",
 "new": "采购代理服务费。资格预审文件……由采购人支付。"}

// ✅ 正确：这是纯「增加」，改用 insert
{"action": "insert", "anchor": "采购代理服务费。",
 "new": "资格预审文件……由采购人支付。"}
```

**insert 精确落位（run 内切分）：**
`insert_after_text` 已支持「锚点结束位置落在 run 内部时精确切分该 run、在锚点正后方插入」，因此锚点可以选在句中（如「采购代理服务费」「附件 1」），不必避让 run 边界。生成的 INS 紧贴锚点之后，原文零删除。

---

## 四、多段落单元格处理

表格单元格可能包含多个段落（Ctrl+Enter 换行），如职称字段"高级\n计师"。这种场景不能一次搜索两个段落的内容，必须**逐段落分别处理**。

**❌ 不要** 在 P1 做 del+空 ins 然后留着空行

**✅ 正确做法**（以"高级\n计师"→"高级会计师"为例）：
1. P0: del "高级" ins "高级会计师"（替换 + 补充）
2. P0: 增加独立 del "计师"（把 P1 的内容删到 P0 中跟踪）
3. 从 XML 中删除 P1 段落元素
4. 结果：P0 仅剩 [del:高级][del:计师][ins:高级会计师]，无空白段落

---

## 五、批注操作规范

### 5.1 Word 批注

- **作者署名：** 默认"文档修订批注助手"，可由清单 `author` 字段覆盖
- **纯文本规则（强制）：** Word 批注中**绝对不显示颜色图标/emoji**（🔴🟡🟢🔵⚠️✅❌ 等任何 emoji），仅用纯文本描述。生成批注后必须验证每条批注文本不含 emoji 字符
- **默认批注格式：** `【修改建议】原文"xxx"，建议改为"yyy"` — 用户可自定义格式，用户指定的批注文本**原样写入**
- **批注文本规范（annotation-spec）：** 建议格式 `修改 | 第十三条 | 修改理由`，包含修改类型、条款定位、修改理由三要素
- **空单元格锚定：** python-docx 的 `add_comment()` 不要求段落必须有文本内容——**空段落也可以作为批注的锚定对象**。当单元格为空时：优先找第一个非空段落；全空时用 `cell.paragraphs[0]` 作为锚定段落
- 已封装为 `add_comment_to_cell()` 函数，支持空单元格场景

#### 5.1.1 执行顺序：先修订，后批注（用户明确要求）

**❌ 错：** 先加批注再做修订 —— 修订重建段落时会把批注标记 deepcopy，锚定范围漂移。
**✅ 对：** 严格两阶段：
1. **阶段 1 修订**：lxml 直接生成全部 w:del / w:ins / 格式修订（跨 run、先删后增），记录每处修订的 DEL/INS 的 w:id
2. **阶段 2 批注**：修订全部完成后，用 docx_comments 的 `CommentManager.add_comment()` 创建批注内容，再手动把 commentRangeStart / commentRangeEnd / commentReference 移到修订元素上（按 w:id 定位）

#### 5.1.2 批注精确锚定规则（用户强制，2026-08-26 固化）

**位置铁律（同级；合并批注可跨段）：**
- `commentRangeStart` 必须放在它所标注的**第一个修订元素之前**
- `commentRangeEnd` 必须放在它所标注的**最后一个修订元素之后**
- 均在段落直接子元素层操作（DEL/INS/run 是 `w:p` 直接子元素），**不嵌套**；单处批注不跨段，同条款合并批注经 `add_comment_anchored_multi` 支持跨段；`_move_comment_markers` 对锚定元素做直接子元素断言，违反即抛错

| 操作 | 锚定范围 | XML 结构 |
|------|----------|----------|
| 修改 replace（DEL+INS） | Start 在第一个 DEL 前 → End 在最后一个 INS 后 | `commentRangeStart` → DEL… → INS → `commentRangeEnd` → reference run |
| 增加 insert | INS 前 → INS 后 | `commentRangeStart` → INS → `commentRangeEnd` → reference run |
| 删除 delete | 第一个 DEL 前 → 最后一个 DEL 后 | `commentRangeStart` → DEL… → `commentRangeEnd` → reference run |
| 格式修订 format（run 级） | 被改格式的 w:r 前 → 该 run 后 | `commentRangeStart` → run → `commentRangeEnd` → reference run |

**批注文本标注对应条目（用户强制）：** 修订类批注自动追加一行
- 修改类（同时含 DEL+INS）：`本条对应第X条的删除+新增`
- 纯删除：`本条对应第X条的删除`；纯插入：`本条对应第X条的新增`；格式修订：`本条对应第X条的格式修订`
- X 优先取 `item.clause` / `item.条款号`（制度审核场景的条款号，如「第二十二条」），否则用清单条目序号 `idx+1`（与输出 tag `[N]` 一致）；批注文本已含「本条对应」时不重复追加

实现 `_move_comment_markers(p_elem, comment_id, start_elem, end_elem)`：
1. 在段落中按 `w:id` 找到该批注的 3 个标记（crs / cre / cref_run，cref 在 `w:r > w:commentReference` 内）
2. 断言 start_elem / end_elem 均为 p_elem 直接子元素且 start 在 end 前（保证同级、顺序正确）；跨段合并批注用 `add_comment_anchored_multi`：crs 在首段首个修订元素前、cre/cref 在末段末个修订元素后
3. 依次 `remove` 后按新位置插入：crs 插到 start_elem 前，cre 插到 end_elem 后，cref_run 紧跟 cre
4. 段落没有任何 `w:r` 时（整段被删除），先临时插入空 `w:r` 供 CM 锚定，移动完标记后移除

#### 5.1.3 WPS / Word 双兼容（强制）

WPS 显示批注比 Word 严格得多，必须满足：

1. **使用 docx_comments 创建批注基础设施**——它同时生成 4 个部件：
   `comments.xml`、`commentsExtended.xml`、`commentsIds.xml`、`commentsExtensible.xml`
   **只手工写 comments.xml 时，Word 正常显示但 WPS 完全不显示批注！**
2. **修订 id 从 10000 起**，避免与文档已有修订（w:del/w:ins 的 w:id）冲突
3. **修订时间用 `+08:00` 时区格式**：`datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M:%S+08:00')`
4. 批注 XML 需含 `w14`/`w15`/`mc` 命名空间声明与 `mc:Ignorable="w14 w15"`、`w14:paraId`/`w14:textId` 属性（docx_comments 自动生成，勿手工精简）
5. 修订标记 run 的 rPr：**原 run 无 rPr 时绝不凭空创建**（Word 依据 w:del/w:ins 元素自动渲染删除线/下划线）；有 rPr 时追加 `w:rStyle val="Del"/"Ins"`

---

## 六、格式修订规范（action=format）

> 内容修订改文字（w:del/w:ins）；**格式修订只改格式、不动文字**，通过属性层可追踪变更实现：
> - 字符格式（level=run）：`w:rPr` 内追加 `w:rPrChange`（内嵌旧 `w:rPr`）
> - 段落格式（level=para）：`w:pPr` 内追加 `w:pPrChange`（内嵌旧 `w:pPr`）
> `*PrChange` 必须是其父属性元素的**最后一个子元素**；新格式是属性元素的当前子元素，旧格式快照在 `*PrChange` 内。

### 6.1 何时用格式修订

**只改格式、文字不变**的场景必须用 `action=format`，禁止用 `replace` 把格式问题当内容改：
- 标题/正文加粗、去加粗、改字号、改字体、改颜色
- 段落对齐、行距、首行缩进

### 6.2 JSON 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `action` | 是 | `format` |
| `scope` | 是 | `para`（正文段落）\| `cell`（表格单元格） |
| `para_index` | scope=para | 段落索引（0 起始） |
| `table`/`row`/`cell` | scope=cell | 单元格坐标（0 起始） |
| `level` | 是 | `run`（字符格式）\| `para`（段落格式） |
| `run_text` | 否 | level=run 时：仅改该文本所在 run；省略=整段所有 run |
| `new_format` | 是 | 新格式语义键值对（见 6.3） |
| `comment` | 否 | 批注内容 |

### 6.3 new_format 键值表（语义键 → OOXML）

**字符格式（level=run）：**

| 键 | 类型 | 说明 | 映射 |
|----|------|------|------|
| `bold` | bool | 加粗 | `w:b` + `w:bCs`（true=裸元素，false=删除） |
| `italic` | bool | 斜体 | `w:i` + `w:iCs` |
| `underline` | bool | 下划线 | `w:u w:val="single"` |
| `font` | str | 字体名（中英文统一） | `w:rFonts`（ascii/hAnsi/eastAsia/cs） |
| `font_size_pt` | number | 字号（磅） | `w:sz` + `w:szCs`（val=磅×2） |
| `color` | str | 颜色 RRGGBB | `w:color w:val` |

**段落格式（level=para）：**

| 键 | 类型 | 说明 | 映射 |
|----|------|------|------|
| `align` | str | 对齐 | `w:jc`（left/center/right/both/distribute） |
| `line_spacing` | number | 行距倍数 | `w:spacing`（line=倍数×240，lineRule=auto） |
| `first_line_indent_pt` | number | 首行缩进（磅） | `w:ind`（firstLine=磅×20） |

**规则：**
- 键值设为 `false`/`None` 表示「移除该格式」（布尔开关 false=关闭并删除元素）。
- 未在键值表中的键忽略；`new_format` 为空时该条目视为失败（跳过并提示）。

### 6.4 旧格式快照（自动捕获，无需用户指定）

脚本自动把**修改前**的属性快照写入 `*PrChange`，用户**无需**提供 old 格式，只需给 `new_format`。批注里可自行描述「旧→新」（如「16pt 加粗 → 22pt 不加粗」），脚本只负责落修订标记。

### 6.5 批注锚定

- level=run：批注锚定到被改格式的 `w:r`（精确到 run）
- level=para：批注锚定到整个段落（段落标记）

### 6.6 已知限制

- 仅覆盖上表列出的常见格式键；复杂的（如字距 w:kern、字符间距、底纹 shd 等）当前未纳入，需扩展 `_apply_run_format`。
- 段落级格式修订作用于「段落标记（¶）」，单元格内多段落时作用于首个非空段落。
- `w:spacing` 的 before/after 未单独暴露（仅 line_spacing），改行距时保留原有 before/after 属性。

---

## 七、文件格式检测

- `.doc` 扩展名不一定是二进制 Word 文档，可能是 **RTF 格式**（文件头 `{\rtf1\`）
- RTF 和二进制 .doc 的处理方式不同；本技能脚本基于 python-docx，只支持 .docx
- **遇到 .doc / .rtf：** 先检查文件头确认真实格式；如需处理，先用 LibreOffice 转换为 .docx（`soffice --headless --convert-to docx`），转换后需检查列宽等格式误差（可能引入 ±1~4 twip 误差）
- 处理前先检查文件头确认真实格式

---

## 八、依赖环境

```bash
pip install python-docx docx-comments lxml
```

| 依赖 | 用途 |
|------|------|
| `python-docx>=1.1.0` | Word 文档解析与修订 |
| `docx-comments>=0.3.0` | Word 批注（CommentManager） |
| `lxml>=4.9.0` | WordprocessingML XML 底层操作 |
