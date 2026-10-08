#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读查询技能内置 law.db，供制度审核提供可追溯候选法条。"""
import argparse, json, os, sqlite3

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "lawdb", "law.db")

def lookup(db, query=None, article_id=None, title=False, level=None, status="现行有效", limit=20):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    params = []
    if article_id is not None:
        sql = """SELECT a.id article_id, a.law_id, l.name law_name, l.doc_no, l.level,
                         l.status, l.effective_date, a.chapter_no, a.chapter_name,
                         a.article_no, a.content
                  FROM articles a JOIN laws l ON l.id=a.law_id WHERE a.id=?"""
        params.append(article_id)
    elif title:
        sql = """SELECT NULL article_id, l.id law_id, l.name law_name, l.doc_no,
                         l.level, l.status, l.effective_date, NULL chapter_no,
                         NULL chapter_name, NULL article_no, NULL content
                  FROM laws l WHERE (l.name LIKE ? OR COALESCE(l.doc_no,'') LIKE ?)"""
        params += [f"%{query}%", f"%{query}%"]
    else:
        q = (query or '').strip()
        if len(q) <= 2:
            # LIKE 兜底：trigram 对 2 字以内查询无结果，改走全表子串匹配
            # （条文 1.5 万条量级，毫秒级；通配符转义避免 % _ 被当作模式）
            escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            sql = """SELECT a.id article_id, a.law_id, l.name law_name, l.doc_no,
                             l.level, l.status, l.effective_date, a.chapter_no,
                             a.chapter_name, a.article_no, a.content
                      FROM articles a JOIN laws l ON l.id=a.law_id
                      WHERE a.content LIKE ? ESCAPE '\\'"""
            params.append(f"%{escaped}%")
        else:
            # FTS5 trigram 检索（3 字以上）
            sql = """SELECT a.id article_id, a.law_id, l.name law_name, l.doc_no,
                             l.level, l.status, l.effective_date, a.chapter_no,
                             a.chapter_name, a.article_no, a.content
                      FROM articles_fts f JOIN articles a ON a.id=f.article_ref
                      JOIN laws l ON l.id=a.law_id
                      WHERE f.content MATCH ?"""
            # 将用户输入作为字面量短语，避免百分号、括号等字符触发 FTS5 查询语法错误。
            params.append('"' + q.replace('"', '""') + '"')
    clauses = []
    if status:
        clauses.append("l.status=?"); params.append(status)
    if level:
        clauses.append("l.level=?"); params.append(level)
    if clauses: sql += " AND " + " AND ".join(clauses)
    if article_id is None: sql += " ORDER BY l.id, a.article_no LIMIT ?" if not title else " ORDER BY l.id LIMIT ?"
    if article_id is None: params.append(limit)
    rows = [dict(r) for r in con.execute(sql, params)]
    con.close()
    return rows

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=DEFAULT_DB)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--query")
    g.add_argument("--article-id", type=int)
    p.add_argument("--title", action="store_true", help="将 query 作为法规标题/文号直查")
    p.add_argument("--level")
    p.add_argument("--status", default="现行有效", help="默认只查现行有效；传空字符串可取消筛选")
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()
    rows = lookup(args.db, args.query, args.article_id, args.title, args.level, args.status, args.limit)
    print(json.dumps({"count": len(rows), "results": rows}, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
