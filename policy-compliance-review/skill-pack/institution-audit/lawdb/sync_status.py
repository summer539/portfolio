#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按用户 3 个结构化文件核对 law.db 时效性（status）。
匹配键：标题(去空白) + 公布日期；同名多版本靠日期区分；待确认直接写入不核查。
用法: python3 sync_status.py [--dry-run]"""
import re, sys, json, sqlite3, os
from collections import Counter

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "law.db")
FILES = [
    ("upload/2026/09/01/结构化-国家法律法规-20260901115834.json", "法律/法律相关"),
    ("upload/2026/09/01/结构化-司法解释-20260901115900.json", "司法解释"),
    ("upload/2026/09/01/结构化-行政法规-20260901115913.json", "行政法规"),
]

SX_MAP = {"有效": "现行有效", "已废止": "已废止", "已修改": "已修改",
          "尚未生效": "尚未生效", "待确认": "待确认"}


def norm(s):
    """清洗标题：去空白、尾部_/+噪声、_hash尾缀、++、'（附：...'截断"""
    t = re.sub(r"\s+", "", s or "")
    t = re.sub(r"_[0-9a-f]{6,}$", "", t)  # flk 文件名 hash 尾缀
    t = t.rstrip("_+")
    t = t.replace("++", "")
    t = re.sub(r"（附：.*$", "", t)
    return t





def norm_date(d):
    d = str(d or "").strip()
    if re.match(r"^\d{8}$", d):
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def main():
    dry = "--dry-run" in sys.argv
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 库内索引：norm_title -> [(id, publish_date, doc_no, status)]
    db_idx = {}
    db_clean = {}  # clean_title -> [(id, publish_date, status)]
    for r in cur.execute("SELECT id, name, publish_date, doc_no, status FROM laws"):
        db_idx.setdefault(norm(r["name"]), []).append(r)
        db_clean.setdefault(norm(r["name"]), []).append(r)

    total_match = total_update = 0
    by_file = {}
    unmatched = []
    multi_hits = []
    for path, lvl in FILES:
        with open(path, encoding="utf-8") as f:
            recs = json.load(f)["记录"]
        st = Counter()
        upd = Counter()
        for r in recs:
            title = norm(r["标题"])
            date = norm_date(r.get("公布日期"))
            sx = SX_MAP.get(r.get("时效性"), r.get("时效性"))
            cands = [x for x in db_idx.get(title, []) if x["publish_date"] == date]
            used_fallback = False
            if not cands and not date:
                # 回退：日期为空 → 清洗标题匹配库内日期也为空的记录（唯一才更）
                ct = norm(r["标题"])
                pool = [x for x in db_clean.get(ct, []) if x["publish_date"] is None]
                if len(pool) == 1:
                    cands = pool
                    used_fallback = True
            if not cands:
                unmatched.append((lvl, r["标题"], date, sx))
                st["未匹配"] += 1
                continue
            if len(cands) > 1:
                multi_hits.append((lvl, r["标题"], date, [c["id"] for c in cands]))
            for c in cands:
                st["匹配"] += 1
                total_match += 1
                if c["status"] != sx:
                    upd[sx] += 1
                    total_update += 1
                    if not dry:
                        cur.execute("UPDATE laws SET status=? WHERE id=?", (sx, c["id"]))
                else:
                    upd["(同值跳过)"] += 1
        by_file[lvl] = {"记录": len(recs), "匹配": st["匹配"], "未匹配": st["未匹配"],
                        "待更新": sum(upd.values()) - upd.get("(同值跳过)", 0), "明细": dict(upd)}
        print(f"\n[{lvl}] 记录{len(recs)} | 匹配{st['匹配']} 未匹配{st['未匹配']} | 待更新{by_file[lvl]['待更新']}")
        print(f"   更新明细: {dict(upd)}")

    print(f"\n{'='*60}\n合计匹配 {total_match} | 待更新 {total_update}")
    if unmatched:
        print(f"\n⚠ 未匹配 {len(unmatched)} 条（库内无同标题同日期记录）:")
        for lvl, t, d, sx in unmatched[:40]:
            print(f"   [{lvl}] {t[:45]} | {d} | {sx}")
    if multi_hits:
        print(f"\n⚠ 同名同日期多条 {len(multi_hits)} 组（需文号辅助）:")
        for lvl, t, d, ids in multi_hits[:20]:
            print(f"   [{lvl}] {t[:45]} | {d} | ids={ids}")
    if not dry:
        con.commit()
        print("\n✅ 已写入数据库")
    con.close()


if __name__ == "__main__":
    main()
