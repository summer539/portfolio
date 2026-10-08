#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
司法解释/国家法律法规缺失正文补充脚本
====================================
数据来源：用户修复版提取 JSON（含完整"正文"字段）
处理：对库内"只有截断题注/公布通告、无实质正文"的记录，
      用用户正文更新 full_text/preamble/effective_date，articles 重建为全文单条。
不动：一致项、实质不一致项（另列反馈清单）。
"""
import json
import re
import sqlite3
import sys
import time
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "law.db")
RESULT = os.path.join(BASE, "check_supplement_result.json")
FILES = [
    ("国家法律法规", "upload/2026/09/01/补充-缺失正文-国家法律法规 (1)-20260901101237.json"),
    ("司法解释", "upload/2026/09/01/补充-缺失正文-司法解释-20260901101255.json"),
]


def clean_title(t):
    t = (t or '').strip()
    t = re.sub(r'_[0-9a-f]{8}$', '', t)
    t = re.sub(r'_+$', '', t)
    t = t.replace('++', ' ')
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def norm(s):
    return re.sub(r'\s+', '', s or '')


def extract_effective_date(text):
    for pat in [r"自(\d{4})年(\d{1,2})月(\d{1,2})日起施行",
                r"自(\d{4})年(\d{1,2})月(\d{1,2})日施行",
                r"自(\d{4})年(\d{1,2})月(\d{1,2})日起实施"]:
        m = re.search(pat, text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def main():
    t0 = time.time()
    with open(RESULT, encoding="utf-8") as f:
        result = json.load(f)

    con = sqlite3.connect(DB)
    cur = con.cursor()

    # 处理期间禁用 FTS 清理触发器（trigram 索引逐条删除极慢），重建索引后恢复
    TRG_SQL = "CREATE TRIGGER trg_articles_fts_del AFTER DELETE ON articles BEGIN DELETE FROM articles_fts WHERE article_ref = OLD.id; END"
    cur.execute("DROP TRIGGER IF EXISTS trg_articles_fts_del")
    con.commit()

    # 库内索引
    cur.execute("SELECT id, name, publish_date FROM laws")
    laws = cur.fetchall()
    by_key = {}
    by_name = {}
    for lid, name, pub in laws:
        by_key.setdefault((clean_title(name), pub), []).append(lid)
        by_name.setdefault(clean_title(name), []).append(lid)

    to_fix = []  # (law_id, 标题, 用户正文, 用户题注)
    for tag, path in FILES:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        recs = data["记录"]
        by_rec = {(clean_title(r.get("标题")), _norm_pub(r.get("公布日期"))): r for r in recs}
        for item in result[tag]["库内缺正文→待补充"]:
            title = item["标题"]
            pub = item["公布日期"]
            r = by_rec.get((clean_title(title), pub)) or by_rec.get((clean_title(title), _norm_pub(pub)))
            if not r:
                print(f"!! 清单记录未找到: {title} | {pub}")
                continue
            lids = by_key.get((clean_title(title), pub)) or by_key.get((clean_title(title), _norm_pub(pub)))
            if not lids:
                lids = by_name.get(clean_title(title), [])
                if len(lids) > 1:
                    # 多个候选：优先日期一致
                    dated = [l for l in lids if True]  # 保持原序，日期为空的记录一般唯一
            if not lids:
                print(f"!! 库内未匹配: {title} | {pub}")
                continue
            to_fix.append((lids[0], title, (r.get("正文") or "").strip(), (r.get("题注") or "").strip()))

    print(f"待补充: {len(to_fix)} 条")
    if "--dry-run" in sys.argv:
        print("dry-run，不写库")
        return

    updated = 0
    for lid, title, body, preamble in to_fix:
        if not body:
            continue
        eff = extract_effective_date(body) or extract_effective_date(preamble)
        # 题注优先用正文首段（若为（...）格式），否则用用户题注字段
        first_line = body.split("\n")[0].strip()
        if first_line.startswith("（") and first_line.endswith("）"):
            preamble_final = first_line
        elif first_line.startswith("(") and first_line.endswith(")"):
            preamble_final = first_line
        else:
            preamble_final = preamble or None
        cur.execute(
            "UPDATE laws SET full_text=?, preamble=?, effective_date=COALESCE(?, effective_date) WHERE id=?",
            (body, preamble_final, eff, lid),
        )
        cur.execute("DELETE FROM articles WHERE law_id=?", (lid,))
        cur.execute(
            "INSERT INTO articles (law_id, chapter_no, chapter_name, article_no, content) VALUES (?,NULL,NULL,1,?)",
            (lid, body),
        )
        updated += 1
        if updated % 100 == 0:
            con.commit()
            print(f"  已更新 {updated} ...")

    con.commit()
    print(f"更新完成: {updated} 条")

    # 重建 FTS
    print("重建 articles_fts ...")
    cur.execute("DELETE FROM articles_fts")
    cur.execute("INSERT INTO articles_fts(content, article_ref) SELECT content, id FROM articles")
    # 恢复触发器
    cur.execute(TRG_SQL)
    con.commit()

    cur.execute("SELECT count(*) FROM laws")
    print("laws:", cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM articles")
    print("articles:", cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM articles_fts")
    print("fts:", cur.fetchone()[0])
    con.close()
    print(f"耗时 {time.time()-t0:.1f}s")


def _norm_pub(s):
    s = str(s or "").strip()
    d = re.sub(r"\D", "", s)
    if len(d) == 8:
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
    return s


if __name__ == "__main__":
    main()
