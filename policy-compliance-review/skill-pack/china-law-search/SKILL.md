---
name: china-law-search
description: 中国国家法律法规数据库（flk.npc.gov.cn）查询工具。支持法规搜索、详情查看、状态检查、按日期筛选新发布法规、批量状态核查。触发词：法律法规、法规查询、法规检索、法规状态、法规废止、法规修订、新发布法规、flk、国家法律法规数据库、china law、law search、规章查询、部门规章、地方规章、国家规章库、规章检索、gov.cn规章。
slug: nigo-china-law-search
displayName: 国家法律法规查询
version: 1.1.0
summary: 中国国家法律法规数据库（flk.npc.gov.cn）查询工具，支持法规搜索、详情查看、状态检查、按日期筛选新发布法规、批量状态核查。
license: MIT
---

# 中国法律法规统一查询

统一查询入口，自动先查国家法律法规数据库（flk.npc.gov.cn），查不到再 fallback 到国家规章库（gov.cn）。

覆盖范围：
- 国家法律法规数据库：宪法、法律、行政法规、地方法规、司法解释、监察法规
- 国家规章库：部门规章、地方政府规章

## 数据源清单（已验证 2026-08-26）

本技能的全部检索数据来源如下。**标注 ✅ 的为已验证可访问的官方源**；所有官方网址均为政府/官方机构域名，非商业转载站。

### 一、官方法规数据库（自动两库联查）

| # | 数据源 | 官方网址 | 覆盖范围 | 访问方式 |
|---|---|---|---|---|
| 1 | 国家法律法规数据库 | https://flk.npc.gov.cn/ | 宪法、法律、行政法规、地方法规、司法解释、监察法规 | 公开 API，无需认证（`scripts/lib/flk_api.py`）✅ |
| 2 | 国家规章库（中国政府网） | https://www.gov.cn/zhengce/xxgk/gjgzk/index.htm | 部门规章、地方政府规章（仅收录现行有效） | 需动态 athenaappkey，脚本自动刷新（`scripts/lib/gov_api.py`）✅ |

### 二、官方网抓取渠道（两库查不到的法规/文件）

| # | 数据源 | 官方网址 | 用途 | 状态 |
|---|---|---|---|---|
| 3 | 中国政府网 | https://www.gov.cn/ | 国家政策法规、党内法规官方受权发布 | ✅ 200 |
| 4 | 共产党员网（中央组织部） | https://www.12371.cn/ | 党内法规全文（党章、准则、条例等），**党内法规首选** | ✅ 200 |
| 5 | 人民网党建频道 | http://dangjian.people.com.cn/ | 党建类法规转载 | ✅ 200（偶发连接超时，有备用源） |
| 6 | 中央党校（国家行政学院） | https://www.ccps.gov.cn/ | 党建理论、党内法规发布 | ✅ 200 |
| 7 | 财政部 | https://www.mof.gov.cn/ | 财政领域法规、党内法规转载；会计司 `kjs.mof.gov.cn`（财会〔XXXX〕XXXX号 政策发布） | ✅ 200 |
| 8 | 工业和信息化部 | https://www.miit.gov.cn/ | 通信行业标准/规定发布、党内法规转载；地方管局（如 `cqca.miit.gov.cn` 重庆管局）存有标准 PDF | ✅ 200 |
| 9 | 国家发展改革委 | https://www.ndrc.gov.cn/ | 发改委规范性文件（发改法规规〔XXXX〕XXXX号）、委令，**规范性文件兜底源** | ✅ 200 |
| 10 | 国务院国资委 | https://www.sasac.gov.cn/ | 国资委规范性文件（国资发改革〔XXXX〕XXXX号、国资委令） | ✅ http 200 / wap 200（https 直连不稳） |
| 11 | 中国证监会 | https://www.csrc.gov.cn/ | 证监会公告、监管规则适用指引、境外发行上市配套文件 | ✅ 200（附件 PDF 需按 cID 规则拼 URL） |
| 12 | 住房城乡建设部 | https://www.mohurd.gov.cn/ | 工程建设标准发布公告（GB 系列） | ✅ 200 |
| 13 | 最高人民法院 | https://www.court.gov.cn/ | 司法解释 | ✅ 301 正常 |
| 14 | 最高人民检察院 | https://www.spp.gov.cn/ | 司法解释 | ✅ 200 |
| 15 | 新华社 | https://www.xinhuanet.com/ | 法律法规受权发布（党内法规补录首选之一） | ✅ 200 |

> ⚠️ 曾用但**已失效**：财政部会计资格评价中心全文库 `kzp.mof.gov.cn`（2026-08-26 实测 410 Gone）——老财会文件改从 mof.gov.cn 主站/会计司栏目获取。

### 三、香港法规官方源

| # | 数据源 | 官方网址 | 用途 | 状态 |
|---|---|---|---|---|
| 16 | 香港交易所规则网 | https://cn-rules.hkex.com.hk/ | 港交所《上市规则》、附录守则（C1 企业管治守则、C3 董事证券交易标准守则等） | ✅ 200；沙箱环境直连不稳，走 `https://sc.hkex.com.hk/TuniS/` 代理 |
| 17 | 香港电子版法例 | https://www.elegislation.gov.hk/ | 香港法例全文（如证券及期货条例 571 章、公司条例 622 章） | ✅ 302 正常；有客户端检测，需 playwright-cli JS 渲染 |
| 18 | 香港公司注册处 | https://www.cr.gov.hk/ | 公司条例 622 章及附属法例导航（cap622A-N） | ✅ 200 |

### 四、备用渠道（非官方，仅首选源不可用时）

| # | 数据源 | 官方网址 | 用途 | 状态 |
|---|---|---|---|---|
| 19 | 上观新闻（解放日报社） | https://www.shobserver.com/ | 官方文件转载（如人民网连接失败时的备用） | ⚠️ 302 正常，媒体转载站非权威源，**入库必须标注来源** |

> 约定：官方法规数据库（flk/规章库）查不到的文件 → 走二/三节官方源 → 仍不可用才用第四节备用源。数据源选用细则见 `assets/data-source-rules.md`；各源的详细查找方式（栏目路径/搜索技巧/附件规则）见 institution-audit 技能 `lawdb/SOURCES.md`。

## When to Use

- 查询某条法律法规/规章是否仍然有效
- 搜索某个关键词相关的法律法规或规章
- 查找某个日期之后新发布的法律法规
- 批量检查一批法规的当前状态（自动两库联查）
- 从 Excel 读取法规清单，批量检查有效性并输出 Excel 结果
- 查询新发布法规并直接输出 Excel
- 批量下载法规全文（docx）
- 下载法规全文（docx/pdf）
- **将法规入库到本地 law.db（官方网抓取 → 解析 → 入库，一键可复现）**

## 安装说明

1. 将本目录（`china-law-search/`）放置到目标智能体的 skills 目录（如 `~/.openclaw/skills/` 或工作区 `skills/`）。
2. 核心查询功能零第三方依赖（仅 Python 标准库）。
3. 可选依赖见 `config/requirements.txt`：
   - Excel 导入/导出功能需 `openpyxl`
   - 国家规章库（gov.cn）访问密钥自动刷新需 `playwright-cli`（npm 包，首次使用时脚本自动检测并安装，无需手动处理）
   - root 环境 Chromium 配置见 `config/playwright-config.json`
4. 首次使用国家规章库查询时，脚本自动获取访问密钥并缓存到 `scripts/lib/.athena_key_cache.json`（自动生成，请勿提交/分享）。

## 快速用法

### Python API（AI Agent 推荐用法）

```python
import sys
# 将下方路径替换为实际安装路径（本技能所在目录下的 scripts/）
sys.path.insert(0, "<技能安装路径>/china-law-search/scripts")
import law_search

# ── 搜索 ──
result = law_search.unified_search("安全生产法")
result = law_search.unified_search("危险化学品 安全管理", content_search=True)

# ── 批量检查 ──
results = law_search.unified_batch_check(["法规名称1", "法规名称2"])

# ── 从Excel批量检查并输出Excel（一步到位，支持断点续查）──
law_search.batch_check_to_excel(
    input_excel="法律法规清单.xlsx",
    output_excel="法规有效性查询结果.xlsx",
    col="B",              # 法规名称所在列
    start_row=2,           # 数据起始行（跳过表头）
    progress_file="check_progress.json",  # 断点续查进度文件
)

# ── 查询新发布法规并输出Excel ──
law_search.new_since_to_excel("2026-01-01", "2026年新发布法规.xlsx")

# ── 批量下载全文（查询→转格式→下载→重试，格式转换见 references/output-format.md）──
check_progress = {}  # 由 unified_batch_check 结果转换而来
law_search.batch_download_from_check(
    check_progress=check_progress,
    output_dir="./下载",
    delay=0.5,
    dl_progress_file="download_progress.json",
)

# ── 单独调用某个库 ──
from lib import flk_api, gov_api   # scripts/lib/ 下，sys.path 指向 scripts 即可
flk_api.search("安全生产法", exact=True)
gov_api.search("商品房屋租赁管理办法")
flk_api.download_file("bbbs_id", output_dir="./downloads")
gov_api.download_as_docx("商品房屋租赁管理办法", output_dir="./downloads")
```

### CLI

```bash
LAW=<技能安装路径>/china-law-search/scripts/law_search.py

# ── 搜索 ──
python3 $LAW search "安全生产法"
python3 $LAW search "安全生产法" --exact
python3 $LAW search "危险化学品 安全管理" --content
python3 $LAW search "消防安全" --content --all-pages

# ── 批量检查 ──
python3 $LAW batch-check laws.txt
python3 $LAW batch-check laws.txt --json

# ── 从Excel批量检查并输出Excel ──
python3 $LAW check-excel 法律法规清单.xlsx -o 查询结果.xlsx --col B --progress progress.json

# ── 查询新发布法规并输出Excel ──
python3 $LAW new-since-excel 2026-01-01 -o 2026年新发布法规.xlsx

# ── 查找新发布法规（文本输出）──
python3 $LAW new-since 2025-03-09
python3 $LAW new-since 2025-03-09 --all-types --all-pages --json

# ── 下载 ──
python3 $LAW download <bbbs_id> --output ./downloads
python3 $LAW batch-download check_result.json --output ./downloads

# ── 从检查进度批量下载 ──
python3 $LAW download-from-check progress.json -o ./下载 --dl-progress dl_progress.json
```

### 入库到本地 law.db（法规导入器）

```bash
LAWDB_IMPORT=<技能安装路径>/china-law-search/scripts/lawdb_import.py

# 单部
python3 $LAWDB_IMPORT one --name "XXX条例" --url "https://..." --org "机关" \
    --pub 2024-01-01 --eff 2024-01-01 [--preamble "题注"] [--level 党内法规] [--db /path/law.db]

# 批量（JSON 清单，模板见 references/batch-entries.example.json）
python3 $LAWDB_IMPORT batch entries.json --db /path/law.db

# 两库预检（每行一个法规名）
python3 $LAWDB_IMPORT precheck names.txt
```

```python
import sys
sys.path.insert(0, "<技能安装路径>/china-law-search/scripts")
import lawdb_import

con = lawdb_import.init_db("/path/law.db")
n = lawdb_import.import_law_from_url(
    con, name="XXX条例", url="https://官方源/...",
    org="发布机关", publish_date="2024-01-01", effective_date="2024-01-01",
    preamble="题注（可空）", doc_no="文号（可空）",
    level="党内法规", status="现行有效", official_url=None)
summary = lawdb_import.import_batch(con, [ {...}, {...} ])  # 批量
found, missing = lawdb_import.check_two_libraries(["法规名1", "法规名2"])  # 两库预检
chapters, articles = lawdb_import.parse_html(lawdb_import.fetch("https://..."))  # 纯解析调试
```

## 文件结构

```
china-law-search/
├── SKILL.md                    # 本文件（入口 + 快速参考）
├── _meta.json                  # 发布元数据
├── assets/                     # 规范和规则
│   ├── data-source-rules.md    # 数据源规范（两库优先/官方源白名单/查不到的处理）
│   ├── import-rules.md         # 入库规范（标准流程/字段约定/解析规则/命名）
│   ├── known-issues.md         # 已知问题与经验（API变化/解析坑/athenaappkey运维）
│   └── maintenance-rules.md    # Key Rules + 自我进化规则 + 目录维护约定
├── references/                 # 输出模板
│   ├── batch-entries.example.json  # 批量入库 JSON 清单模板
│   ├── output-format.md            # 查询结果字段说明 + 下载格式转换
│   └── progress-files.example.md   # 断点续查/续下进度文件结构
├── config/                     # 对接系统环境配置
│   ├── README.md               # 配置说明 + athenaappkey 手动刷新流程
│   ├── playwright-config.json  # playwright-cli 浏览器配置（root 免沙箱）
│   └── requirements.txt        # Python 依赖清单
└── scripts/                    # 脚本与 API 模块
    ├── law_search.py           # 统一入口（推荐使用）
    ├── lawdb_import.py         # 法规导入器（官方网 → 本地 law.db，自包含）
    └── lib/                    # Python 包（原 lib/）
        ├── __init__.py
        ├── flk_api.py          # 国家法律法规数据库 API
        ├── gov_api.py          # 国家规章库 API
        └── refresh_gov_key.js  # playwright-cli 刷新 athenaappkey 脚本
```

## 核心函数一览

| 函数 | 用途 | 输入 | 输出 |
|---|---|---|---|
| `unified_search()` | 统一搜索（两库） | 关键词 | dict |
| `unified_batch_check()` | 批量检查状态 | 名称列表 | list |
| `batch_check_to_excel()` | Excel→批量检查→Excel | 输入Excel路径 | 输出Excel |
| `new_since_to_excel()` | 新发布法规→Excel | 日期 | Excel文件 |
| `unified_new_since()` | 新发布法规查询 | 日期 | dict |
| `batch_download_from_check()` | 批量下载全文 | 检查进度dict | 下载进度dict |
| `lawdb_import.import_law_from_url()` | 官方网→入库单部 | 名称/URL/元数据 | 条文数 |
| `lawdb_import.import_batch()` | 批量入库（幂等） | entries dict列表 | summary列表 |
| `lawdb_import.check_two_libraries()` | 两库预检 | 名称列表 | (found, missing) |
| `lawdb_import.parse_html()` | 纯解析调试（不入库） | HTML字符串 | (chapters, articles) |

## 详细文档索引

| 主题 | 位置 |
|---|---|
| 数据源优先级、官方源白名单、查不到的处理 | `assets/data-source-rules.md` |
| 入库标准流程、字段约定、解析/命名规则 | `assets/import-rules.md` |
| 已知问题与踩坑经验（API 变化、解析坑、密钥运维） | `assets/known-issues.md` |
| 批量废止法规导入流程（flk 反爬分批 + 断点续做） | `assets/batch-abolish-workflow.md` |
| Key Rules、自我进化规则、目录维护约定 | `assets/maintenance-rules.md` |
| 查询结果字段、下载格式转换、文件命名模板 | `references/output-format.md` |
| 批量入库 JSON 清单模板 | `references/batch-entries.example.json` |
| 断点续查/续下进度文件结构 | `references/progress-files.example.md` |
| 环境配置、athenaappkey 手动刷新流程 | `config/README.md` |
