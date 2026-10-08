# -*- coding: utf-8 -*-
"""法规库校验工具：对库内法规重新从官方源下载全文，逐条比对条文内容
用法:
  python3 verify_lawdb.py            # 校验全部法规
  python3 verify_lawdb.py 1          # 只校验指定 law_id
"""
import sys, os, sqlite3, urllib.request, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "law.db")
SKILLS_DIR = os.path.dirname(BASE)  # .../skills/
SKILL = os.path.join(SKILLS_DIR, "china-law-search")
sys.path.insert(0, f"{SKILL}/scripts")
sys.path.insert(0, SKILL)
sys.path.insert(0, BASE)

from build_lawdb import parse_docx
from lib import flk_api, gov_api

def fetch_flk_docx(bbbs):
    """从 flk 官方下载 docx，返回临时文件路径"""
    info = flk_api.download_info(bbbs, fmt="docx")
    req = urllib.request.Request(info["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    fd, path = tempfile.mkstemp(suffix=".docx")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path

def fetch_gov_docx(name):
    """从规章库下载 docx，返回临时文件路径"""
    out = gov_api.download_as_docx(name, output_dir=tempfile.mkdtemp())
    return out

def verify_law(con, law):
    law_id, name, bbbs, source = law["id"], law["name"], law["bbbs"], law["source"]
    print(f"\n{'='*64}\n校验: [{law_id}] {name}（{source}）\n{'='*64}")
    # 1. 从官方源重新获取全文
    try:
        if source == "国家规章库":
            docx_path = fetch_gov_docx(name)
        else:
            if not bbbs:
                print("  ⚠️ 无 bbbs，跳过（无法从官方源核验）")
                return None
            docx_path = fetch_flk_docx(bbbs)
    except Exception as e:
        print(f"  ❌ 官方下载失败: {e}")
        return None

    # 2. 解析官方全文
    try:
        _, _, official_articles, meta = parse_docx(docx_path)
    except Exception as e:
        print(f"  ❌ 官方全文解析失败: {e}")
        return None
    os.unlink(docx_path) if os.path.exists(docx_path) else None

    # 3. 对比条文数
    db_arts = {r["article_no"]: r["content"]
               for r in con.execute("SELECT article_no, content FROM articles WHERE law_id=?", (law_id,))}
    off_arts = {a["no"]: a["content"] for a in official_articles}
    print(f"  条文数: 库内={len(db_arts)} vs 官方={len(off_arts)} "
          f"{'✅' if len(db_arts)==len(off_arts) else '❌'}")

    # 4. 逐条对比内容
    only_db = set(db_arts) - set(off_arts)
    only_off = set(off_arts) - set(db_arts)
    diff = [no for no in set(db_arts) & set(off_arts) if db_arts[no] != off_arts[no]]
    if only_db: print(f"  ❌ 库内独有条文: {sorted(only_db)}")
    if only_off: print(f"  ❌ 官方独有条文: {sorted(only_off)}")
    if diff:
        print(f"  ❌ 内容不一致条文: {sorted(diff)}")
        for no in sorted(diff)[:5]:
            print(f"     - 第{no}条 库内: {db_arts[no][:60]}...")
            print(f"       第{no}条 官方: {off_arts[no][:60]}...")
    if not only_db and not only_off and not diff:
        print(f"  ✅ 全部 {len(db_arts)} 条条文与官方源逐字一致")
    return {"law_id": law_id, "name": name, "db": len(db_arts),
            "off": len(off_arts), "diff": diff, "only_db": only_db, "only_off": only_off}

def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    if len(sys.argv) > 1:
        laws = con.execute("SELECT * FROM laws WHERE id=?", (int(sys.argv[1]),)).fetchall()
    else:
        laws = con.execute("SELECT * FROM laws ORDER BY id").fetchall()
    print(f"待校验法规: {len(laws)} 部")
    results = []
    for law in laws:
        r = verify_law(con, law)
        if r: results.append(r)
    # 汇总
    print(f"\n{'='*64}\n汇总\n{'='*64}")
    for r in results:
        status = "✅ 一致" if not r["diff"] and not r["only_db"] and not r["only_off"] else "❌ 有差异"
        print(f"  [{r['law_id']}] {r['name']}: {status}（库内{r['db']}条/官方{r['off']}条）")
    con.close()

if __name__ == "__main__":
    main()
