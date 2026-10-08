#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""law.db 全面数据健康检查（离线）
覆盖：A 基础一致性 / B 重复与冲突 / C 字段完整性 / D 内容质量 / E 状态合理性 / F 规模统计"""
import sqlite3, re, sys, os
from collections import Counter

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "law.db")
VALID_STATUS = {"现行有效", "已废止", "已修改", "待确认", "尚未生效"}
VALID_LEVELS = {"法律", "行政法规", "部门规章", "地方性法规", "地方政府规章",
                "司法解释", "规范性文件", "党内法规", "香港法规", "企业制度"}

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()
issues = []  # (类别, 严重度, 描述)


def issue(cat, sev, msg):
    issues.append((cat, sev, msg))


print("=" * 70)
print("A. 基础一致性")
print("=" * 70)
n_laws = cur.execute("SELECT count(*) FROM laws").fetchone()[0]
n_arts = cur.execute("SELECT count(*) FROM articles").fetchone()[0]
n_fts = cur.execute("SELECT count(*) FROM articles_fts").fetchone()[0]
print(f"  laws={n_laws} | articles={n_arts} | fts={n_fts}")
if n_arts != n_fts:
    issue("A", "高", f"articles({n_arts}) != articles_fts({n_fts})，FTS 索引不一致")
else:
    print("  ✅ FTS 数量一致")
# 孤儿条文
orphans = cur.execute("""SELECT count(*) FROM articles a LEFT JOIN laws l ON a.law_id=l.id
                         WHERE l.id IS NULL""").fetchone()[0]
if orphans:
    issue("A", "高", f"孤儿条文 {orphans} 条（law_id 无对应 laws）")
else:
    print("  ✅ 无孤儿条文")
# 无条文 laws
no_art = cur.execute("""SELECT count(*) FROM (SELECT l.id FROM laws l LEFT JOIN articles a
                        ON a.law_id=l.id GROUP BY l.id HAVING count(a.id)=0)""").fetchone()[0]
print(f"  无条文记录(全文单条或空): {no_art} 部")
# FTS 完整性：article_ref 有效性（LEFT JOIN 走主键，勿用 NOT IN + LIMIT）
fts_bad = cur.execute("""SELECT count(*) FROM articles_fts f
                         LEFT JOIN articles a ON f.article_ref=a.id
                         WHERE a.id IS NULL""").fetchone()[0]
if fts_bad:
    issue("A", "高", f"FTS article_ref 无效 {fts_bad} 条")
else:
    print("  ✅ FTS article_ref 全部有效")

print()
print("=" * 70)
print("B. 重复与冲突")
print("=" * 70)
# 同名同日期重复
dups = cur.execute("""SELECT name, publish_date, count(*) c, group_concat(id) ids
                      FROM laws GROUP BY name, publish_date HAVING c>1 ORDER BY c DESC""").fetchall()
print(f"  同名同日期重复: {len(dups)} 组")
for d in dups:
    print(f"    ⚠ {d['name'][:40]} | {d['publish_date']} | {d['c']}条 ids={d['ids']}")
    issue("B", "中", f"同名同日期重复: {d['name'][:40]} ids={d['ids']}")
# 同名多版本 status 合理性：最新版应为 现行有效/已废止/待确认，旧版应为已修改/已废止
print("\n  同名多版本 status 合理性抽查:")
bad_ver = []
for r in cur.execute("""SELECT name, publish_date, status FROM laws
                        WHERE name IN (SELECT name FROM laws GROUP BY name HAVING count(*)>1)
                        ORDER BY name, publish_date"""):
    bad_ver.append(r)
# 按 name 分组检查
from collections import defaultdict
groups = defaultdict(list)
for r in bad_ver:
    groups[r["name"]].append(r)
suspect_ver = []
for name, vers in groups.items():
    dates = [v["publish_date"] for v in vers if v["publish_date"]]
    if not dates:
        continue
    latest = max(dates)
    for v in vers:
        if v["publish_date"] == latest and v["status"] in ("已修改", "已被修改"):
            suspect_ver.append((name, v["publish_date"], v["status"], "最新版标已修改"))
        if v["publish_date"] != latest and v["status"] == "现行有效":
            # 旧版现行有效：可能合理（如废止决定未出），列为观察
            suspect_ver.append((name, v["publish_date"], v["status"], "旧版标现行有效(观察)"))
if suspect_ver:
    for s in suspect_ver[:20]:
        print(f"    ? {s[0][:36]} | {s[1]} | {s[2]} | {s[3]}")
        issue("B", "低" if "观察" in s[3] else "中", f"多版本状态存疑: {s[0][:36]} {s[1]} {s[2]} {s[3]}")
    print(f"    共 {len(suspect_ver)} 条存疑")
else:
    print("  ✅ 多版本状态标注未见异常")
# 同 bbbs 重复
bbbs_dup = cur.execute("""SELECT bbbs, count(*) c FROM laws WHERE bbbs IS NOT NULL AND bbbs!=''
                          GROUP BY bbbs HAVING c>1""").fetchall()
print(f"  同 bbbs 重复: {len(bbbs_dup)} 组")

print()
print("=" * 70)
print("C. 字段完整性")
print("=" * 70)
name_empty = cur.execute("SELECT count(*) FROM laws WHERE name IS NULL OR trim(name)=''").fetchone()[0]
date_empty = cur.execute("SELECT count(*) FROM laws WHERE publish_date IS NULL OR publish_date=''").fetchone()[0]
date_bad = cur.execute("""SELECT count(*) FROM laws WHERE publish_date IS NOT NULL AND publish_date!=''
                          AND publish_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'""").fetchone()[0]
level_bad = cur.execute("""SELECT count(*) FROM laws WHERE level IS NULL OR level='' OR level NOT IN
                           ('法律','行政法规','部门规章','地方性法规','地方政府规章','司法解释','规范性文件','党内法规','香港法规','企业制度')""").fetchone()[0]
status_bad = cur.execute(f"""SELECT count(*) FROM laws WHERE status IS NULL OR status NOT IN
                             {tuple(VALID_STATUS)}""").fetchone()[0]
org_empty = cur.execute("SELECT count(*) FROM laws WHERE issuing_org IS NULL OR issuing_org=''").fetchone()[0]
docno_empty = cur.execute("SELECT count(*) FROM laws WHERE doc_no IS NULL OR doc_no=''").fetchone()[0]
bbbs_empty = cur.execute("SELECT count(*) FROM laws WHERE bbbs IS NULL OR bbbs=''").fetchone()[0]
src_bad = cur.execute("SELECT count(*) FROM laws WHERE source IS NULL OR source=''").fetchone()[0]
print(f"  name 为空: {name_empty}")
print(f"  publish_date 为空: {date_empty} | 格式非法: {date_bad}")
print(f"  level 缺失/非法: {level_bad}")
print(f"  status 非法值: {status_bad}")
print(f"  issuing_org 缺失: {org_empty} ({org_empty*100//n_laws}%)")
print(f"  doc_no 缺失: {docno_empty} ({docno_empty*100//n_laws}%)")
print(f"  bbbs 缺失: {bbbs_empty} ({bbbs_empty*100//n_laws}%)")
print(f"  source 为空: {src_bad}")
for cat, sev, msg in [("C", "高", f"publish_date 空 {date_empty} 条"), ("C", "高", f"publish_date 格式非法 {date_bad} 条"),
                      ("C", "高", f"level 缺失/非法 {level_bad} 条"), ("C", "高", f"status 非法 {status_bad} 条"),
                      ("C", "中", f"name 空 {name_empty} 条")]:
    if int(msg.split()[-2]) > 0:
        issue(cat, sev, msg)
# 标题噪声
noise = cur.execute("""SELECT id, name FROM laws WHERE name LIKE '%++%' OR name LIKE '%_%' ESCAPE '\\' 
                       OR name LIKE '%（附：%' OR name GLOB '*_[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*'""").fetchall()
# LIKE 转义问题，简单点：用正则查
noise = [r for r in cur.execute("SELECT id, name FROM laws").fetchall()
         if re.search(r"\+{2,}|_[0-9a-f]{6,}$|（附：", r["name"])]
print(f"  标题含噪声(++/_hash/（附：截断): {len(noise)} 条")
for r in noise[:10]:
    print(f"    ! id={r['id']} | {r['name'][:50]}")
    issue("C", "低", f"标题噪声: id={r['id']} {r['name'][:40]}")

print()
print("=" * 70)
print("D. 内容质量")
print("=" * 70)
# full_text 过短
short_ft = cur.execute("""SELECT id, name, length(full_text) fl, level FROM laws
                          WHERE full_text IS NULL OR length(full_text)<50 ORDER BY fl""").fetchall()
print(f"  full_text 空或<50字: {len(short_ft)} 条")
for r in short_ft[:15]:
    print(f"    ! id={r['id']} | {r['level']} | {r['name'][:40]} | {r['fl']}字")
    issue("D", "中", f"全文过短: id={r['id']} {r['name'][:36]} {r['fl']}字")
# content 超短
short_ct = cur.execute("""SELECT count(*) FROM articles WHERE content IS NULL OR length(content)<10""").fetchone()[0]
print(f"  条文 content 空或<10字: {short_ct} 条")
if short_ct:
    issue("D", "中", f"条文过短 {short_ct} 条")
# article_no 异常
bad_no = cur.execute("""SELECT count(*) FROM articles WHERE article_no IS NULL OR article_no<=0""").fetchone()[0]
dup_no = cur.execute("""SELECT count(*) FROM (SELECT law_id, article_no, count(*) c FROM articles
                        GROUP BY law_id, article_no HAVING c>1)""").fetchone()[0]
print(f"  article_no 空/<=0: {bad_no} | 同 law 内 article_no 重复: {dup_no}")
if bad_no: issue("D", "中", f"article_no 异常 {bad_no} 条")
if dup_no: issue("D", "低", f"article_no 组内重复 {dup_no} 组")
# 条文编号连续性（每 law：count == max(article_no) 且 min==1）
gap_laws = cur.execute("""SELECT law_id, count(*) c, min(article_no) mn, max(article_no) mx FROM articles
                          GROUP BY law_id HAVING c != mx OR mn != 1""").fetchall()
print(f"  条文编号不连续(1..N 有缺口): {len(gap_laws)} 部")
for r in gap_laws[:10]:
    print(f"    ! law_id={r['law_id']} | 条数={r['c']} min={r['mn']} max={r['mx']}")
    issue("D", "低", f"条文编号不连续 law_id={r['law_id']} c={r['c']} 1..{r['mx']}")
# 条文数异常：法律/行政法规条文数<5
few_art = cur.execute("""SELECT l.id, l.name, l.level, count(a.id) c FROM laws l
                         JOIN articles a ON a.law_id=l.id
                         WHERE l.level IN ('法律','行政法规') GROUP BY l.id HAVING c<5""").fetchall()
print(f"  法律/行政法规 条文数<5: {len(few_art)} 部")
for r in few_art[:10]:
    print(f"    ! id={r['id']} | {r['level']} | {r['name'][:40]} | {r['c']}条")
    issue("D", "中", f"条文异常少: id={r['id']} {r['name'][:36]} {r['c']}条")
# preamble 截断迹象
trunc_preamble = cur.execute("""SELECT id, name FROM laws WHERE preamble IS NOT NULL AND preamble!=''
                                AND (preamble LIKE '%检察委员会' OR preamble LIKE '%审判委员会'
                                     OR preamble LIKE '%常务委员会' OR preamble LIKE '%会议通过')
                                AND preamble NOT LIKE '%）'""").fetchall()
print(f"  preamble 疑似截断(以'委员会/会议通过'结尾无闭合): {len(trunc_preamble)} 条")
if trunc_preamble:
    issue("D", "低", f"preamble 疑似截断 {len(trunc_preamble)} 条（flk 提取局限，正文不受影响）")

print()
print("=" * 70)
print("E. 状态合理性")
print("=" * 70)
no_art_by_status = cur.execute("""SELECT l.status, count(*) c FROM laws l
                                  LEFT JOIN articles a ON a.law_id=l.id
                                  GROUP BY l.id HAVING count(a.id)=0
                                  ORDER BY 2 DESC""").fetchall()
# 上面 GROUP BY l.id 后 select l.status 会取组内任意行，SQLite 允许；再按 status 聚合
from collections import Counter as _C
_st = _C()
for r in cur.execute("""SELECT l.status FROM laws l LEFT JOIN articles a ON a.law_id=l.id
                        GROUP BY l.id HAVING count(a.id)=0"""):
    _st[r[0]] += 1
print(f"  无条文记录按状态: {dict(_st)}")
eff_missing = cur.execute("""SELECT count(*) FROM laws WHERE status='尚未生效'
                             AND (effective_date IS NULL OR effective_date='')""").fetchone()[0]
print(f"  尚未生效但 effective_date 缺失: {eff_missing} 条")
if eff_missing:
    issue("E", "低", f"尚未生效缺 effective_date {eff_missing} 条")
# 待确认分布
tk = cur.execute("SELECT level, count(*) FROM laws WHERE status='待确认' GROUP BY level").fetchall()
print(f"  待确认: {dict(tk)}")
# 已废止/已修改 但正文为空
dead_empty = cur.execute("""SELECT count(*) FROM laws WHERE status IN ('已废止','已修改')
                            AND (full_text IS NULL OR length(full_text)<30)""").fetchone()[0]
print(f"  已废止/已修改 但全文<30字: {dead_empty} 条")
if dead_empty:
    issue("E", "中", f"已废止/已修改全文过短 {dead_empty} 条")

print()
print("=" * 70)
print("F. 规模统计")
print("=" * 70)
print("  按层级:")
for r in cur.execute("SELECT level, count(*) FROM laws GROUP BY level ORDER BY 2 DESC"):
    print(f"    {r[0]}: {r[1]}")
print("  按来源:")
for r in cur.execute("SELECT source, count(*) FROM laws GROUP BY source ORDER BY 2 DESC"):
    print(f"    {r[0]}: {r[1]}")
print("  按状态:")
for r in cur.execute("SELECT status, count(*) FROM laws GROUP BY status ORDER BY 2 DESC"):
    print(f"    {r[0]}: {r[1]}")
print("  按年份(公布):")
for r in cur.execute("""SELECT substr(publish_date,1,4) y, count(*) FROM laws
                        WHERE publish_date IS NOT NULL GROUP BY y ORDER BY y DESC LIMIT 8"""):
    print(f"    {r[0]}: {r[1]}")

print()
print("=" * 70)
print("汇总")
print("=" * 70)
if not issues:
    print("  ✅ 未发现异常")
else:
    by_cat = Counter(i[0] for i in issues)
    by_sev = Counter(i[1] for i in issues)
    print(f"  发现 {len(issues)} 项异常 | 类别: {dict(by_cat)} | 严重度: 高{by_sev.get('高',0)} 中{by_sev.get('中',0)} 低{by_sev.get('低',0)}")
    for cat, sev, msg in issues:
        print(f"    [{cat}/{sev}] {msg}")
con.close()
