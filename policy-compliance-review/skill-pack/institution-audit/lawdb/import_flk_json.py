#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flk 结构化 JSON 批量入库脚本（幂等）
====================================
数据来源：国家法律法规数据库（flk）批量下载的结构化提取 JSON
判重规则：按 (name, publish_date) 精确匹配，库内已有则跳过
处理类型：
  1. 条文型（含"第X条"结构）→ 逐条入库，article_no=文本编号，content 去掉条号前缀
  2. 条目型（修正案/决定类"一、二、三…"）→ 逐条入库，article_no=顺序号，content 保留原文
  3. 无条文无条目（纯决定/决议类）→ 全文单条入库
导入完成后重建 articles_fts 全文索引（FTS5 trigram）。
"""
import json
import re
import sqlite3
import sys
import time
import argparse
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "law.db")
JSON_PATH = "upload/2026/08/28/结构化-国家法律法规-20260828144850.json"
SOURCE = "国家法律法规数据库(flk)批量下载"
OFFICIAL_URL = "https://flk.npc.gov.cn/"

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def clean_title(t):
    """清理标题噪声：尾部 hash、尾部下划线、++ 符号"""
    if not t:
        return t
    t = t.strip()
    t = re.sub(r"_[0-9a-f]{8}$", "", t)
    t = re.sub(r"_+$", "", t)
    t = t.replace("++", " ")
    return t.strip()


def parse_date(s):
    """YYYYMMDD → YYYY-MM-DD；非法/空 → None"""
    s = str(s or "").strip()
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) == 4:
        return f"{digits}-01-01"
    return s or None


def cn_num_to_int(cn):
    """中文数字条号转整数：第一条→1，第一百五十八条→158"""
    if not cn:
        return None
    total, section = 0, 0
    for ch in cn:
        if ch in CN_DIGITS:
            section = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            total += (section if section else 1) * CN_UNITS[ch]
            section = 0
    return total + section


def extract_article_no(content):
    """从"第一条　xxx"提取 (条号整数, 去掉前缀后的正文)"""
    m = re.match(r"^第([零一二三四五六七八九十百千]+)条[\s　]*", content)
    if m:
        return cn_num_to_int(m.group(1)), content[m.end():].strip()
    return None, content.strip()


def extract_effective_date(preamble):
    """从题注提取施行日期，提取不到返回 None"""
    if not preamble:
        return None
    for pat in [r"自(\d{4})年(\d{1,2})月(\d{1,2})日起施行",
                r"自(\d{4})年(\d{1,2})月(\d{1,2})日施行",
                r"自(\d{4})年(\d{1,2})月(\d{1,2})日起实施"]:
        m = re.search(pat, preamble)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def extract_org(preamble):
    """从题注提取制定/修正机关（只取题注中实际出现的官方机构名）"""
    if not preamble:
        return None
    for org in ["全国人民代表大会常务委员会", "全国人民代表大会", "国务院", "中央军事委员会",
                "最高人民法院", "最高人民检察院"]:
        if org in preamble:
            return org
    return None


def dedup_chapters(chapters):
    """章节目录去重（保留首次出现顺序；flk 提取偶有重复两遍）"""
    seen, out = set(), []
    for c in chapters or []:
        c = (c or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def build_full_text(title, preamble, chapters, articles, items):
    """拼接全文：题注 + 章节目录 + 条文/条目全文"""
    parts = []
    if preamble:
        parts.append(preamble)
    chapters = dedup_chapters(chapters)
    if chapters:
        parts.append("章节目录：" + "；".join(chapters))
    if articles:
        parts.append("\n".join(a["内容"] for a in articles))
    if items:
        parts.append("\n".join(items))
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--json", default=JSON_PATH)
    ap.add_argument("--level", default="法律", help="入库层级，如 法律/行政法规（默认 法律）")
    ap.add_argument("--default-status", default="现行有效",
                    help="JSON 时效性字段缺失时使用的状态（默认 现行有效）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args()

    t0 = time.time()
    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    recs = data["记录"]
    print(f"JSON 记录数: {len(recs)}")
    print(f"入库层级: {args.level} | 时效性缺失默认状态: {args.default_status}")

    con = sqlite3.connect(args.db)
    cur = con.cursor()

    # 库内现有 (name, publish_date) 集合
    cur.execute("SELECT name, publish_date FROM laws")
    existing = {(n, p) for n, p in cur.fetchall()}
    print(f"库内 laws 总数: {len(existing)}")

    # 预构建"同标题最大公布日期"（库内 + JSON 内），用于旧版本自动标"已修改"
    title_max = {}
    for n, p in existing:
        if n and p and p > title_max.get(n, ""):
            title_max[n] = p
    for r in recs:
        t = clean_title(r.get("标题"))
        p = parse_date(r.get("公布日期"))
        if t and p and p > title_max.get(t, ""):
            title_max[t] = p

    stats = {"条文型": 0, "条目型": 0, "无结构": 0, "跳过": 0, "新增": 0}
    skipped_detail = []
    inserted_laws = 0
    inserted_articles = 0
    batch = []

    for idx, r in enumerate(recs):
        title = clean_title(r.get("标题"))
        pub = parse_date(r.get("公布日期"))
        sxx = r.get("时效性")
        if sxx == "有效":
            status = "现行有效"
        elif sxx == "失效":
            status = "已废止"
        else:
            status = args.default_status
            # JSON 未提供时效性时：同标题存在更新版本 → 旧版标"已修改"（库内多版本惯例）
            if status == "现行有效" and pub and title_max.get(title, "") > pub:
                status = "已修改"
        preamble = (r.get("题注") or "").strip() or None
        articles = r.get("条文") or []
        items = r.get("条目") or []
        chapters = dedup_chapters(r.get("章节目录"))

        # 判重：同名同公布日期已在库 → 跳过
        if (title, pub) in existing:
            stats["跳过"] += 1
            skipped_detail.append((title, pub, status, len(articles) + len(items)))
            continue

        # 类型统计（dry-run 也统计）
        if articles:
            stats["条文型"] += 1
        elif items:
            stats["条目型"] += 1
        else:
            stats["无结构"] += 1

        stats["新增"] += 1
        if args.dry_run:
            inserted_laws += 1
            inserted_articles += (len(articles) + len(items)) or 1
            continue

        full_text = build_full_text(title, preamble, chapters, articles, items)
        eff = extract_effective_date(preamble)
        org = extract_org(preamble)

        cur.execute(
            """INSERT INTO laws (name, doc_no, level, issuing_org, publish_date, amend_date,
                                 status, full_text, bbbs, source, official_url, effective_date, preamble)
               VALUES (?, NULL, ?, ?, ?, NULL, ?, ?, NULL, ?, ?, ?, ?)""",
            (title, args.level, org, pub, status, full_text, SOURCE, OFFICIAL_URL, eff, preamble),
        )
        law_id = cur.lastrowid
        inserted_laws += 1

        # 条文型
        if articles:
            for a in articles:
                content = (a.get("内容") or "").strip()
                if not content:
                    continue
                no, body = extract_article_no(content)
                if no is None:  # 无"第X条"前缀的兜底
                    no = len(articles)  # 不理想，但保留原文
                    body = content
                batch.append((law_id, None, None, no, body))
                inserted_articles += 1
        # 条目型（修正案/决定类：一、二、三…）
        elif items:
            for i, it in enumerate(items, 1):
                it = (it or "").strip()
                if it:
                    batch.append((law_id, None, None, i, it))
                    inserted_articles += 1
        # 无条文无条目：全文单条
        else:
            body = preamble or title
            batch.append((law_id, None, None, 1, body))
            inserted_articles += 1

        if len(batch) >= 200:
            cur.executemany(
                "INSERT INTO articles (law_id, chapter_no, chapter_name, article_no, content) VALUES (?,?,?,?,?)",
                batch,
            )
            batch = []
            con.commit()

    if batch:
        cur.executemany(
            "INSERT INTO articles (law_id, chapter_no, chapter_name, article_no, content) VALUES (?,?,?,?,?)",
            batch,
        )
    con.commit()

    if not args.dry_run:
        # 重建 FTS 全文索引（本库为普通 FTS5 表：rebuild/delete-all 命令均无效，
        # 正确方式：DELETE 清空后从 articles 全量插入，与 lawdb_import.py 一致）
        print("重建 articles_fts 全文索引（DELETE + 全量插入）...")
        cur.execute("DELETE FROM articles_fts")
        cur.execute("INSERT INTO articles_fts(content, article_ref) SELECT content, id FROM articles")
        con.commit()

    # 汇总
    cur.execute("SELECT count(*) FROM laws")
    total_laws = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM articles")
    total_articles = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM articles_fts")
    total_fts = cur.fetchone()[0]
    con.close()

    print(f"\n=== 导入汇总 ===")
    print(f"新增法规: {inserted_laws} 部")
    print(f"新增条文: {inserted_articles} 条")
    print(f"类型分布: {stats}")
    print(f"跳过(已在库): {stats['跳过']} 条")
    print(f"库内最新规模: laws={total_laws} / articles={total_articles} / fts={total_fts}")
    print(f"耗时: {time.time()-t0:.1f}s")

    # 跳过的明细（供人工核查版本）
    if skipped_detail:
        print(f"\n=== 跳过的记录（已在库，共 {len(skipped_detail)} 条）===")
        for t, p, s, n in skipped_detail[:50]:
            print(f"  {t} | {p} | {s} | 条文数:{n}")
        if len(skipped_detail) > 50:
            print(f"  ... 其余 {len(skipped_detail)-50} 条略")


if __name__ == "__main__":
    main()
