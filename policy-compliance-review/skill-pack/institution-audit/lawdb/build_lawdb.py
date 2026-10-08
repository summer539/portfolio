# -*- coding: utf-8 -*-
"""法律法规数据库构建脚本 v2
- parse_docx(path)  : 解析任意法规 docx → (law_name, chapters, articles, meta)
- import_law(...)   : 导入一部法规（支持多版本、自定义状态）
- 命令行直接运行    : 构建单部法规库（兼容 v1 用法）
"""
import docx, re, sqlite3, sys, os

# ---------- 中文数字转阿拉伯数字 ----------
CN_NUM = {"零":0,"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
CN_UNIT = {"十":10,"百":100,"千":1000}
def cn2num(s: str) -> int:
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

def parse_docx(path: str):
    """解析法规 docx，返回 (law_name, chapters, articles, meta)"""
    doc = docx.Document(path)
    paras = [p.text.strip().replace("\u3000", "") for p in doc.paragraphs]

    # 法律名称：正文前第一个含"法"的完整行（排除修正记录、目录）
    law_name = None
    for t in paras:
        if t and re.match(r"^[^\s（(]+(法|条例|规定|办法|细则|规则|章程|决定|公约|条约)$", t):
            law_name = t
            break
    if not law_name:
        for t in paras[:10]:
            if t and ("法" in t or "条例" in t) and "修正" not in t and "通过" not in t and "目录" not in t:
                law_name = t
                break

    # 找目录起止：目录特征是"第X章"后紧跟另一个"第X章"
    toc_start = next((i for i, t in enumerate(paras) if t.startswith("目") and "录" in t), -1)
    is_chapter = lambda t: bool(re.match(r"^第[零一二两三四五六七八九十百千]+章", t))
    is_article = lambda t: bool(re.match(r"^第[零一二两三四五六七八九十百千]+条", t))
    body_start = None
    if toc_start >= 0:
        for i in range(toc_start + 1, len(paras)):
            if is_chapter(paras[i]):
                j = i + 1
                while j < len(paras) and not paras[j]:
                    j += 1
                if j < len(paras) and is_article(paras[j]):
                    body_start = i
                    break
    if body_start is None:
        # 无目录：从第一个章节标题开始（若无章节则从第一个条文开始）
        first_ch = next((i for i, t in enumerate(paras) if is_chapter(t)), None)
        first_art = next((i for i, t in enumerate(paras) if is_article(t)), 0)
        body_start = first_ch if first_ch is not None and first_ch < first_art else first_art
    body = paras[body_start:]

    # 解析章节和条文
    chapters, articles = [], []
    cur_ch, cur_art = 0, None
    for t in body:
        m_ch = re.match(r"^第([零一二两三四五六七八九十百千]+)章(.+)$", t)
        m_art = re.match(r"^第([零一二两三四五六七八九十百千]+)条(.*)$", t)
        if m_ch:
            cur_ch = cn2num(m_ch.group(1))
            chapters.append((cur_ch, m_ch.group(2).replace(" ", "").strip()))
            cur_art = None
        elif m_art:
            no = cn2num(m_art.group(1))
            cur_art = no
            articles.append({"no": no, "chapter": cur_ch, "content": m_art.group(2).strip()})
        elif t and cur_art is not None:
            articles[-1]["content"] += "\n" + t

    # 元数据：从修订记录解析
    rev_text = "".join(t for t in paras[:body_start] if t)
    m_pass = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?通过", rev_text)
    publish_date = f"{m_pass.group(1)}-{int(m_pass.group(2)):02d}-{int(m_pass.group(3)):02d}" if m_pass else None
    m_amend = list(re.finditer(r"根据(\d{4})年(\d{1,2})月(\d{1,2})日", rev_text))
    amend_date = f"{m_amend[-1].group(1)}-{int(m_amend[-1].group(2)):02d}-{int(m_amend[-1].group(3)):02d}" if m_amend else None
    m_org = re.search(r"(第[零一二两三四五六七八九十百千]+届全国人民代表大会(?:常务委员会)?)", rev_text)
    issuing_org = m_org.group(1) if m_org else None
    # 规范化：制定机关不带届次（"第八届全国人民代表大会常务委员会" → "全国人民代表大会常务委员会"）
    if issuing_org:
        issuing_org = re.sub(r"第[零一二两三四五六七八九十百千]+届", "", issuing_org)
    meta = {
        "name": law_name,
        "publish_date": publish_date,
        "amend_date": amend_date,
        "issuing_org": issuing_org,
        "preamble": _extract_preamble("\n".join(t for t in paras if t)),
        "full_text": "\n".join(t for t in paras if t),
    }
    return law_name, chapters, articles, meta

_PAT_PREAMBLE_PAREN = re.compile(r"^[（(].+[）)]$", re.M)
_PAT_PREAMBLE_ZXL = re.compile(r"^(主席令第[零一二三四五六七八九十百\d]+号)\s*\n\s*(.+?通过[^\n]*施行。?)", re.M)

def _extract_preamble(full_text: str):
    """从全文开头提取题注（公布/通过/修正历史），兼容全角/半角括号及主席令两行式"""
    if not full_text:
        return None
    m = _PAT_PREAMBLE_PAREN.search(full_text)
    if m:
        return m.group(0).strip()
    m2 = _PAT_PREAMBLE_ZXL.search(full_text)
    if m2:
        return f"{m2.group(1)} {m2.group(2)}".replace("\n", "")
    return None

def import_law(con, law_id: int, name: str, chapters, articles, meta: dict,
               level="法律", status="现行有效", doc_no=None, bbbs=None, source=None, official_url=None,
               effective_date=None):
    """导入一部法规（含条文 + FTS 索引），返回条文数"""
    cur = con.cursor()
    cur.execute("""INSERT INTO laws (id, name, doc_no, level, issuing_org, publish_date, effective_date, amend_date, status, full_text, preamble, bbbs, source, official_url)
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

def init_db(db_path: str):
    """初始化数据库（建表），已存在则复用"""
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

if __name__ == "__main__":
    # 兼容 v1 用法：python3 build_lawdb.py <docx路径> [状态]
    BASE = os.path.dirname(os.path.abspath(__file__))
    src = sys.argv[1] if len(sys.argv) > 1 else "upload/2026/08/26/中华人民共和国劳动法_20181229-20260826181902.docx"
    status = sys.argv[2] if len(sys.argv) > 2 else "现行有效"
    db = sys.argv[3] if len(sys.argv) > 3 else os.path.join(BASE, "law.db")
    name, chapters, articles, meta = parse_docx(src)
    print(f"解析完成: {name} | {len(chapters)} 章, {len(articles)} 条 | 通过:{meta['publish_date']} 修正:{meta['amend_date']}")
    con = init_db(db)
    next_id = con.execute("SELECT COALESCE(MAX(id),0)+1 FROM laws").fetchone()[0]
    n = import_law(con, next_id, name, chapters, articles, meta, status=status)
    print(f"入库完成: law_id={next_id}, 条文={n}, 状态={status}")
    con.close()
