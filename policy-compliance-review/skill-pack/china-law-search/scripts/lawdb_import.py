#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lawdb_import.py — 法规导入器（官方网抓取 → 解析 → 入库本地 law.db）

设计目标：把"新增法规入库"流程固化为可重复执行的脚本，规避已知坑。

流程（与 SKILL.md「入库到本地 law.db」章节对应）：
1. 两库预检（可选）：flk + 国家规章库，查到的可直接下载 docx 走 build_lawdb；
   查不到的（党内法规/规范性文件等）走官方网抓取
2. 抓取：requests + UA，自动编码探测
3. 解析：正文容器打分 → 清洗 → 起始定位 → 行合并 → 模式判定
   （标准式"第X章/第X条" / 条目式"一、二、三…"）
4. 质量修复：文本编号（支持第一百零一条/第一百一十条）、内嵌条文二次切分、
   尾部噪音截断、UI 噪音清理（绝不删正文标点）
5. 入库：幂等（同名同 level 先删旧）、章节 (序号, 名称) 正确格式、FTS 索引

用法：
    # Python API
    import lawdb_import
    con = lawdb_import.init_db("/path/law.db")
    n = lawdb_import.import_law_from_url(con, name="XXX条例", url="https://...",
                                         org="发布机关", publish_date="2024-01-01",
                                         effective_date="2024-01-01", preamble="题注",
                                         level="党内法规")
    lawdb_import.import_batch(con, [ {...}, {...} ])   # 批量 + 幂等

    # CLI
    python3 lawdb_import.py one --name "X" --url "https://..." --org "机关" \
        --pub 2024-01-01 --eff 2024-01-01 [--preamble "题注"] [--level 党内法规] [--db /path/law.db]
    python3 lawdb_import.py batch entries.json --db /path/law.db
    python3 lawdb_import.py precheck names.txt     # 两库预检，输出查不到的清单

batch JSON 格式（entries.json）：
[
  {"name": "法规名称", "url": "https://...", "org": "发布机关",
   "publish_date": "2024-01-01", "effective_date": "2024-01-01",
   "preamble": "题注/审议批准信息（可空）", "doc_no": "文号（可空）",
   "level": "党内法规", "status": "现行有效"}
]
"""
import re, os, sys, json, time, sqlite3, argparse, copy
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"}

CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9}
CN_UNIT = {"十": 10, "百": 100, "千": 1000}

RE_CH = r"第[零一二两三四五六七八九十百千]+章"
RE_ART = r"第[零一二两三四五六七八九十百千]+条"
RE_NUM = r"([零一二两三四五六七八九十百千]+)"


# ═══════════════════════ 解析层 ═══════════════════════

def cn2num(s: str) -> int:
    """中文数字转阿拉伯。必须支持：零（第一百零一条）、X百Y十（第一百一十条=110）"""
    if s.isdigit():
        return int(s)
    total, section = 0, 0
    for ch in s:
        if ch in CN_NUM:
            section = CN_NUM[ch]
        elif ch in CN_UNIT:
            u = CN_UNIT[ch]
            total += (section if section else 1) * u
            section = 0
    return total + section


def fetch(url, timeout=40, retries=2):
    last = None
    for _ in range(retries + 1):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def extract_text(html):
    """提取正文文本（候选容器打分）。

    坑1：BeautifulSoup 的 get_text(sep) 只在文本节点间插分隔符，
    同一父节点下多个 <p>/<div> 之间不会换行 → 多条条文会连成一行。
    解决：deepcopy 候选节点，把所有块级标签替换为换行后再取文本。
    """
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "iframe", "nav", "header", "footer"]):
        t.decompose()
    best = (0, "")
    for node in soup.find_all(["div", "article", "td", "section"]):
        n = copy.deepcopy(node)
        for tag in n.find_all(["p", "div", "br", "li", "tr", "h1", "h2", "h3",
                               "h4", "h5", "h6", "section", "article"]):
            tag.insert_before("\n")
            tag.unwrap()
        txt = n.get_text("\n", strip=True)
        if not txt:
            continue
        score = 0
        if re.search(RE_CH, txt):
            score += 20
        if re.search(RE_ART, txt):
            score += 10
        if re.search(r"^[一二三四五六七八九十]+、", txt, re.M):
            score += 3
        score += min(len(txt) / 1000, 10)
        if score > best[0]:
            best = (score, txt)
    return best[1]


def clean_lines(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    noise = re.compile(r"^(来源|责任编辑|分享|打印|纠错|相关推荐|版权所有|Copyright|地址：|电话：|邮编：|"
                       r"网站地图|联系我们|主办单位|承办单位|ICP备|京ICP|关闭|上一条|下一条|"
                       r"[\u2605★☆◆◇►▶●○]+$)")
    out = []
    for l in lines:
        if noise.match(l):
            continue
        if len(l) > 200 and l.count(" ") > 30:   # 疑似导航长行
            continue
        out.append(l)
    return out


def merge_lines(lines):
    """按标点/编号前缀决定是否换行。prev 以句号等结尾或新行是编号开头 → 新行。"""
    merged = []
    for l in lines:
        if not merged:
            merged.append(l)
            continue
        prev = merged[-1]
        if (prev.endswith(("。", "；", "：", "，", "、", "！", "？", "”", "“", "）", "》", "号", "项")) or
                re.match(rf"^({RE_CH}|（[一二三四五六七八九十]+）|[一二三四五六七八九十]+、|\d+[\.、])", l) or
                re.match(rf"^{RE_ART}", l)):
            merged.append(l)
        else:
            merged[-1] = prev + l
    return merged


def find_start(lines):
    for i, l in enumerate(lines):
        if re.match(rf"^{RE_CH}", l) or re.match(rf"^{RE_ART}", l) or \
           re.match(r"^[一二三四五六七八九十]+、", l):
            return i
    return 0


def parse_standard(lines):
    """标准式：第X章/第X条。返回 (chapters=[(序号,名称)], articles=[{chapter,no,content}])

    - article_no 用文本编号（支持"第一百五十八条"），而非顺序号
    - 坑2：编号含"零"（第一百零一条）；正则必须带"零"字
    - 坑3：若页面结构异常（<br> 分隔等），多条条文可能合并进一条 content，
      这里做"内嵌第X条"二次切分兜底
    """
    chapters, articles, cur_ch = [], [], None
    for t in lines:
        m_ch = re.match(rf"^{RE_CH}", t)
        m_ar = re.match(rf"^{RE_ART}", t)
        if m_ch:
            ch_name = re.sub(rf"^{RE_CH}[　\s]*", "", t)
            ch_name = re.sub(r"\s+", "", ch_name)
            cur_ch = len(chapters) + 1
            chapters.append((cur_ch, ch_name))
        elif m_ar:
            articles.append({"chapter": cur_ch,
                             "no": cn2num(re.search(rf"第{RE_NUM}条", t).group(1)),
                             "content": t})
        elif articles:
            articles[-1]["content"] += t
    out = []
    for a in articles:
        ms = list(re.finditer(rf"第{RE_NUM}条(?=[　\s])", a["content"]))
        if len(ms) <= 1:
            out.append(a)
            continue
        for i, m in enumerate(ms):
            s = 0 if i == 0 else m.start()
            e = ms[i + 1].start() if i + 1 < len(ms) else len(a["content"])
            seg = a["content"][s:e].strip()
            if seg:
                out.append({"chapter": a["chapter"],
                            "no": a["no"] if i == 0 else cn2num(m.group(1)),
                            "content": seg})
    return chapters, out


def parse_item(lines):
    """条目式：一、二、三… 每块一条（准则/规定/细则类）"""
    blocks, cur = [], []
    for t in lines:
        if re.match(r"^[一二三四五六七八九十]+、", t):
            if cur:
                blocks.append(cur)
            cur = [t]
        else:
            cur.append(t)
    if cur:
        blocks.append(cur)
    return [], [{"chapter": None, "no": i + 1, "content": "\n".join(b)}
                for i, b in enumerate(blocks)]


def trim_tail_noise(merged):
    """尾部截断：去掉文末页面噪音（来源：/编辑：/版权所有/学习专栏…）。

    坑4：这些噪音会被合并进最后一条条文，必须截断；
    关键词只在全文后 25% 范围内匹配，避免误伤正文。
    """
    TAIL = ["来源：新华社", "附件下载：", "相关文章：", "发布日期：", "编辑：",
            "关于我们", "版权所有", "打开微信", "扫一扫", "责任编辑", "用户调查",
            "打印此页", "关闭窗口", "返回顶部", "我要纠错", "学习专栏"]
    cut = len(merged)
    for i, l in enumerate(merged):
        if re.match(r"^（(来源|完|据新华社|责任编辑)", l) or re.match(r"^(完|\(完\))$", l):
            cut = i
            break
        if i > len(merged) * 0.75 and any(k in l for k in TAIL):
            cut = i
            break
    return merged[:cut]


def clean_ui_noise(text):
    """清理正文内残留 UI 噪音。坑5：绝不删正文标点（曾误删 544 条句号）。"""
    t = re.sub(r"[【\[]?(大中小|打印此页|关闭窗口|返回顶部|我要纠错)[】\]]?", "", text)
    t = t.replace("“扫一扫”即可将网页分享至朋友圈。", "")
    t = re.sub(r"（责编：[^）]*）【纠错】$", "", t.strip())
    return t.rstrip()


def parse_html(html):
    """完整解析管线 → (chapters, articles)"""
    text = extract_text(html)
    lines = clean_lines(text)
    start = find_start(lines)
    merged = merge_lines(lines[start:])
    merged = trim_tail_noise(merged)
    has_ch = any(re.match(rf"^{RE_CH}", l) for l in merged)
    has_ar = any(re.match(rf"^{RE_ART}", l) for l in merged)
    if has_ch or has_ar:
        return parse_standard(merged)
    return parse_item(merged)


# ═══════════════════════ 入库层（自包含，不依赖 build_lawdb）═══════════════════════

def init_db(db_path):
    con = sqlite3.connect(db_path)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS laws (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      doc_no TEXT,
      level TEXT,
      issuing_org TEXT,
      publish_date TEXT,
      effective_date TEXT,
      amend_date TEXT,
      status TEXT DEFAULT '现行有效',
      full_text TEXT,
      preamble TEXT,
      bbbs TEXT,
      source TEXT,
      official_url TEXT
    );
    CREATE TABLE IF NOT EXISTS articles (
      id INTEGER PRIMARY KEY,
      law_id INTEGER NOT NULL REFERENCES laws(id),
      chapter_no INTEGER,
      chapter_name TEXT,
      article_no INTEGER,
      content TEXT NOT NULL
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
      content, article_ref UNINDEXED,
      tokenize = 'trigram'
    );
    """)
    return con


def import_law(con, law_id, name, chapters, articles, meta, level="法律", status="现行有效",
               doc_no=None, bbbs=None, source=None, official_url=None, effective_date=None):
    """导入一部法规（含条文 + FTS 索引），返回条文数。

    chapters: [(序号, 章节名), ...]；articles 的 chapter 字段为章节序号。
    坑6：章节必须传 (序号,名称) 元组列表，否则 chapter_name 全空。
    """
    cur = con.cursor()
    cur.execute("""INSERT INTO laws (id, name, doc_no, level, issuing_org, publish_date,
                   effective_date, amend_date, status, full_text, preamble, bbbs, source, official_url)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (law_id, name, doc_no, level, meta.get("issuing_org"),
                 meta.get("publish_date"), effective_date, meta.get("amend_date"), status,
                 meta.get("full_text"), meta.get("preamble"), bbbs, source, official_url))
    art_rows, fts_rows = [], []
    start_id = con.execute("SELECT COALESCE(MAX(id),0)+1 FROM articles").fetchone()[0]
    for i, a in enumerate(articles, start=1):
        ch_name = next((c[1] for c in chapters if c[0] == a["chapter"]), "")
        art_rows.append((start_id + i - 1, law_id, a["chapter"], ch_name, a["no"], a["content"]))
        fts_rows.append((a["content"], start_id + i - 1))
    cur.executemany("INSERT INTO articles VALUES (?,?,?,?,?,?)", art_rows)
    cur.executemany("INSERT INTO articles_fts (content, article_ref) VALUES (?,?)", fts_rows)
    con.commit()
    return len(articles)


def _delete_old(con, name, level):
    for (oid,) in con.execute("SELECT id FROM laws WHERE name=? AND level=?", (name, level)):
        con.execute("DELETE FROM articles WHERE law_id=?", (oid,))
        con.execute("DELETE FROM laws WHERE id=?", (oid,))
    con.commit()


def import_law_from_html(con, name, html, org, publish_date, effective_date,
                         preamble="", doc_no="", level="党内法规", status="现行有效",
                         official_url=""):
    chapters, articles = parse_html(html)
    if not articles:
        raise ValueError(f"解析为空，请检查页面结构（可能不是法规正文页）")
    _delete_old(con, name, level)
    nid = con.execute("SELECT COALESCE(MAX(id),0)+1 FROM laws").fetchone()[0]
    arts = [{"no": a["no"], "chapter": a["chapter"], "content": clean_ui_noise(a["content"])}
            for a in articles]
    meta = {"publish_date": publish_date, "issuing_org": org, "preamble": preamble,
            "full_text": preamble, "source": "官方网站", "official_url": official_url}
    return import_law(con, law_id=nid, name=name, chapters=chapters, articles=arts,
                      meta=meta, level=level, status=status, doc_no=doc_no,
                      effective_date=effective_date, source="官方网站",
                      official_url=official_url)


def import_law_from_url(con, name, url, org, publish_date, effective_date,
                        preamble="", doc_no="", level="党内法规", status="现行有效",
                        official_url=None, delay=0, verbose=True):
    if delay:
        time.sleep(delay)
    html = fetch(url)
    n = import_law_from_html(con, name, html, org, publish_date, effective_date,
                             preamble, doc_no, level, status, official_url or url)
    if verbose:
        print(f"✅ {name}: {n} 条 | {url}")
    return n


def import_batch(con, entries, delay=2):
    """批量导入（幂等）。entries: dict 列表，字段见文件头说明。"""
    summary = []
    for e in entries:
        try:
            n = import_law_from_url(
                con, name=e["name"], url=e["url"], org=e.get("org", ""),
                publish_date=e.get("publish_date"), effective_date=e.get("effective_date"),
                preamble=e.get("preamble", ""), doc_no=e.get("doc_no", ""),
                level=e.get("level", "党内法规"), status=e.get("status", "现行有效"),
                official_url=e.get("official_url"), delay=delay)
            summary.append({"name": e["name"], "articles": n, "url": e["url"]})
        except Exception as ex:
            print(f"❌ {e.get('name')}: {str(ex)[:120]}")
            summary.append({"name": e.get("name"), "error": str(ex)[:120]})
    return summary


def check_two_libraries(names):
    """两库预检：flk + 国家规章库。返回 (查到列表, 未查到列表)。
    未查到的（党内法规/规范性文件）才需要走官方网抓取。
    坑7：unified_batch_check 内部已处理精确匹配，不要自己写匹配逻辑。
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import law_search
        results = law_search.unified_batch_check(names)
        found = [r for r in results if r.get("found")]
        missing = [r for r in results if not r.get("found")]
        return found, missing
    except Exception as e:
        return [], [{"name": n, "found": False, "status": f"预检失败: {e}"} for n in names]


# ═══════════════════════ CLI ═══════════════════════

def _load_entries(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "entries" in data:
        data = data["entries"]
    return data


def main():
    ap = argparse.ArgumentParser(description="法规导入器（官方网 → law.db）")
    ap.add_argument("--db", default=os.environ.get("LAWDB", "skills/institution-audit/lawdb/law.db"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("one", help="导入单部")
    p1.add_argument("--name", required=True)
    p1.add_argument("--url", required=True)
    p1.add_argument("--org", default="")
    p1.add_argument("--pub", required=True, help="公布日期 YYYY-MM-DD")
    p1.add_argument("--eff", required=True, help="施行日期 YYYY-MM-DD")
    p1.add_argument("--preamble", default="")
    p1.add_argument("--doc-no", default="")
    p1.add_argument("--level", default="党内法规")

    p2 = sub.add_parser("batch", help="批量导入 JSON 清单")
    p2.add_argument("entries", help="entries.json 路径")

    p3 = sub.add_parser("precheck", help="两库预检，输出未收录清单")
    p3.add_argument("names", help="法规名列表文件（每行一个）")

    args = ap.parse_args()
    con = init_db(args.db)

    if args.cmd == "one":
        import_law_from_url(con, name=args.name, url=args.url, org=args.org,
                            publish_date=args.pub, effective_date=args.eff,
                            preamble=args.preamble, doc_no=args.doc_no, level=args.level)
        print("完成")
    elif args.cmd == "batch":
        entries = _load_entries(args.entries)
        summary = import_batch(con, entries)
        ok = sum(1 for s in summary if "articles" in s)
        print(f"\n完成 {ok}/{len(summary)} 部")
        json.dump(summary, open(args.entries + ".result.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    elif args.cmd == "precheck":
        names = [l.strip() for l in open(args.names, encoding="utf-8") if l.strip()]
        found, missing = check_two_libraries(names)
        print(f"两库查到 {len(found)} 条：")
        for f in found:
            print(f"  ✅ {f.get('name')} | {f.get('title')} | {f.get('status')}")
        print(f"\n两库未收录 {len(missing)} 条（需官方网抓取）：")
        for m in missing:
            print(f"  ❌ {m.get('name')}")
    con.close()


if __name__ == "__main__":
    main()
