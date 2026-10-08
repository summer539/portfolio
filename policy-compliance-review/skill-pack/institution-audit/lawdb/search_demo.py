# -*- coding: utf-8 -*-
"""FTS5 检索演示：关键词搜索 + 相关度排序 + 高亮"""
import sqlite3, os

con = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "law.db"))

def search(keyword, limit=5, show_hl=True):
    print(f"\n{'='*60}\n🔍 搜索: 「{keyword}」\n{'='*60}")
    sql = """
    SELECT a.article_no, a.chapter_name, a.content,
           bm25(articles_fts) AS score
    FROM articles_fts
    JOIN articles a ON a.id = articles_fts.article_ref
    WHERE articles_fts MATCH ?
    ORDER BY score
    LIMIT ?
    """
    rows = con.execute(sql, (keyword, limit)).fetchall()
    if not rows:
        print("  ❌ 无结果")
        return
    for no, ch, content, score in rows:
        first_line = content.split("\n")[0]
        # 高亮命中片段
        hl = first_line
        for kw in keyword.replace("AND", " ").replace("OR", " ").split():
            kw = kw.strip().strip('"')
            if kw and kw in hl:
                hl = hl.replace(kw, f"【{kw}】")
        print(f"  📌 第{no}条（{ch}） 相关度={score:.2f}")
        print(f"     {hl[:80]}{'…' if len(first_line) > 80 else ''}")

# 演示1：单关键词
search('劳动合同')

# 演示2：多关键词组合（AND）
search('"解除劳动合同" AND "经济补偿"')

# 演示3：前缀匹配（"工时"能命中"工作时间"相关内容）
search('工时')

# 演示4：精确短语
search('"八小时"')

# 演示5：布尔排除（有"解除"但不含"补偿"）
print(f"\n{'='*60}\n🔍 搜索: 「解除劳动合同 NOT 补偿」\n{'='*60}")
rows = con.execute("""
    SELECT a.article_no, a.content FROM articles_fts
    JOIN articles a ON a.id = articles_fts.article_ref
    WHERE articles_fts MATCH '解除劳动合同 NOT 补偿'
    ORDER BY bm25(articles_fts) LIMIT 3
""").fetchall()
for no, content in rows:
    print(f"  📌 第{no}条: {content.split(chr(10))[0][:60]}")

# 演示6：按章节过滤 + 关键词
print(f"\n{'='*60}\n🔍 搜索: 「工资」限定在第十二章(法律责任)\n{'='*60}")
rows = con.execute("""
    SELECT a.article_no, a.content FROM articles_fts
    JOIN articles a ON a.id = articles_fts.article_ref
    WHERE articles_fts MATCH '工资' AND a.chapter_no = 12
    ORDER BY bm25(articles_fts)
""").fetchall()
for no, content in rows:
    print(f"  📌 第{no}条: {content.split(chr(10))[0][:60]}")

# 演示7：查询耗时（100次）
import time
t0 = time.time()
for _ in range(100):
    con.execute("SELECT count(*) FROM articles_fts WHERE articles_fts MATCH '劳动合同'").fetchone()
print(f"\n⚡ 100 次检索总耗时: {(time.time()-t0)*1000:.1f} ms（平均 {(time.time()-t0)*10:.2f} ms/次）")
con.close()
