#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引用核验工具：输入制度文本（docx/txt/直接文本），自动提取《》内法规名，
批量与本地 law.db 比对，输出"引用法规 × 库内状态 × 是否最新"对比表。

用法:
  python3 ref_check.py <file.docx|file.txt|"直接文本"> [--db 路径] [--json 输出json]
示例:
  python3 ref_check.py 制度.docx
  python3 ref_check.py 制度.docx --json ref_result.json
"""
import argparse, json, os, re, sqlite3, sys

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "lawdb", "law.db")

# 《》内提取；排除书名号内明显非法规片段（章节名、附件名等由调用方自行判断）
RE_BOOK = re.compile(r"《([^》]{2,60})》")

# 库内查找时忽略的前缀（简称匹配）
PREFIXES = ["中华人民共和国", "国务院", "国家"]

# 公文外壳归一化：把"中共中央办公厅、国务院办公厅关于印发《X》的通知"等还原为 X
RE_SHELL = re.compile(r"^(?:[^《》]{0,40}?(?:关于)?(?:印发|发布|转发|颁发|批转|同意))?《([^》]+)》")
RE_SUFFIX = re.compile(r"(的通知|的批复|的答复|的复函|的决定|的意见|的公告|的函)$")


def normalize_name(name):
    """名称归一化：提取《》内主体，去掉公文外壳、尾部版本括号、引号。"""
    n = name.strip()
    m = RE_SHELL.search(n)
    if m:
        n = m.group(1)
    else:
        # 无书名号：尝试去"关于…的"外壳
        n = re.sub(r"^(?:关于)?(.+?)(?:的通知|的批复|的答复|的复函|的决定|的意见|的公告|的函)$", r"\1", n)
    n = re.sub(r"[（(](?:19|20)\d{2}年?(?:修正|修订)[）)]$", "", n)  # 尾部（2016修正）等版本标记
    n = n.replace("〈", "").replace("〉", "")
    return n.strip()


def load_text(path):
    """读取 docx 或 txt 全文；其他格式报错。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        import docx
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    if ext == ".txt" or ext == ".md":
        return open(path, encoding="utf-8").read()
    if ext == ".doc":
        # 老格式：尝试 LibreOffice 转换（与废止入库流程一致）
        import subprocess, tempfile
        tmp = tempfile.mkdtemp()
        subprocess.run(["soffice", "--headless", "--convert-to", "txt", path,
                        "--outdir", tmp], check=True, capture_output=True)
        out = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + ".txt")
        return open(out, encoding="utf-8", errors="ignore").read()
    raise ValueError(f"不支持的文件类型: {ext}（支持 docx/txt/md/doc）")


def strip_prefix(name):
    """去掉常见前缀，用于模糊匹配。"""
    for p in PREFIXES:
        if name.startswith(p):
            return name[len(p):]
    return name


def find_in_db(con, name):
    """按名称在 laws 表查找，三级匹配：
    1) 精确 2) 归一化相等（"关于印发《X》的通知"→X）3) 包含兜底（标记 fuzzy）。
    """
    cols = "id, name, doc_no, level, status, publish_date, effective_date, amend_date, source"
    # 1) 精确
    rows = con.execute(f"SELECT {cols} FROM laws WHERE name=?", (name,)).fetchall()
    if rows:
        return rows, False
    # 2) 归一化相等（无条件执行：库名可能带"关于印发《》的通知"外壳或版本括号）
    ref_n = normalize_name(name)
    rows = con.execute(f"SELECT {cols} FROM laws", ()).fetchall()
    hits = [r for r in rows if normalize_name(r[1]) == ref_n]
    if hits:
        return hits, False
    # 3) 包含匹配（引用名在库名中，或库名在引用名中）
    short = strip_prefix(name)
    rows = con.execute(f"SELECT {cols} FROM laws WHERE name LIKE ?", (f"%{short}%",)).fetchall()
    if not rows and short != name:
        rows = con.execute(f"SELECT {cols} FROM laws WHERE name LIKE ?", (f"%{name}%",)).fetchall()
    return rows, True


def pick_latest(rows):
    """多版本取最新（按施行日期，缺省用公布日期；均缺省按 id）。"""
    def key(r):
        d = r[6] or r[5] or ""
        return (d or "", r[0])
    return max(rows, key=key)


def check_one(con, ref):
    """核验单个引用，返回结论 dict。"""
    rows, fuzzy = find_in_db(con, ref)
    if not rows:
        return {"ref": ref, "found": False, "conclusion": "未收录", "detail": "库内无匹配记录（可能为企业内部制度/未收录法规，需人工确认）", "matches": []}

    latest = pick_latest(rows)
    matches = []
    for r in rows:
        matches.append({
            "id": r[0], "name": r[1], "doc_no": r[2], "level": r[3],
            "status": r[4], "publish_date": r[5], "effective_date": r[6],
            "amend_date": r[7], "source": r[8],
        })

    latest_status = latest[4]
    effective = latest[6] or latest[5] or ""
    fuzzy_note = "（近似匹配，建议人工确认）" if fuzzy else ""
    if latest_status == "现行有效":
        if len(rows) > 1:
            outdated = [m for m in matches if m["status"] not in ("现行有效",)]
            note = f"多版本共存（{len(rows)}版），最新施行版为现行有效"
            if outdated:
                note += f"，另有 {len(outdated)} 个旧版本已标注{outdated[0]['status']}"
            return {"ref": ref, "found": True, "conclusion": "现行", "detail": note + fuzzy_note,
                    "matches": matches, "latest": latest[1], "latest_status": latest_status, "doc_no": latest[2],
                    "effective_date": effective}
        return {"ref": ref, "found": True, "conclusion": "现行", "detail": "库内唯一版本，现行有效" + fuzzy_note,
                "matches": matches, "latest": latest[1], "latest_status": latest_status, "doc_no": latest[2],
                "effective_date": effective}
    # 已废止 / 已被修改
    return {"ref": ref, "found": True, "conclusion": "过时", "detail": f"库内最新版状态为『{latest_status}』（公布 {latest[5]}，施行 {effective}），引用已过时" + fuzzy_note,
            "matches": matches, "latest": latest[1], "latest_status": latest_status, "doc_no": latest[2],
            "effective_date": effective}


def run(text, db_path=DEFAULT_DB):
    """主流程：提取引用名 → 批量核验 → 汇总。"""
    refs = []
    seen = set()
    for m in RE_BOOK.finditer(text):
        r = m.group(1).strip()
        if r not in seen:
            seen.add(r)
            refs.append(r)

    con = sqlite3.connect(db_path)
    results = [check_one(con, r) for r in refs]
    con.close()

    cur = sum(1 for x in results if x["conclusion"] == "现行")
    outdated = [x for x in results if x["conclusion"] == "过时"]
    missing = [x for x in results if not x["found"]]
    return {"ref_count": len(refs), "current": cur, "outdated": outdated,
            "missing": missing, "results": results}


def fmt_table(results):
    """文本对比表。"""
    lines = []
    lines.append(f"{'引用名称':<34}{'结论':<6}{'库内匹配/文号':<46}{'状态':<8}{'施行日期'}")
    lines.append("-" * 110)
    for r in results:
        if not r["found"]:
            lines.append(f"{r['ref'][:32]:<34}{'❓未收录':<8}{'-':<46}{'-':<8}{'-'}")
            continue
        name = r["latest"]
        if len(r["matches"]) > 1:
            name = f"{name} 等{len(r['matches'])}版"
        icon = "✅" if r["conclusion"] == "现行" else "⚠️"
        lines.append(f"{r['ref'][:32]:<34}{icon}{r['conclusion']:<4}{name[:38]:<40}"
                     f"{r['latest_status']:<8}{r['effective_date'] or '-'}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="引用核验：制度《》法规名 × law.db 最新版比对")
    ap.add_argument("input", help="docx/txt/md 文件路径，或直接传入文本")
    ap.add_argument("--db", default=DEFAULT_DB, help="法规库路径")
    ap.add_argument("--json", help="结果输出到 JSON 文件")
    args = ap.parse_args()

    if os.path.isfile(args.input):
        text = load_text(args.input)
        src = args.input
    else:
        text = args.input
        src = "<直接文本>"

    out = run(text, args.db)
    print(f"来源: {src}")
    print(f"共提取《》内引用 {out['ref_count']} 个 | ✅ 现行 {out['current']} | ⚠️ 过时 {len(out['outdated'])} | ❓ 未收录 {len(out['missing'])}\n")
    print(fmt_table(out["results"]))
    if out["outdated"]:
        print("\n⚠️ 过时引用明细:")
        for r in out["outdated"]:
            print(f"  《{r['ref']}》 → 库内 {r['latest']}（{r['doc_no'] or '无文号'}，施行 {r['effective_date']}）：{r['detail']}")
    if out["missing"]:
        print("\n❓ 未收录明细（可能为企业内部制度，需人工确认）:")
        for r in out["missing"]:
            print(f"  《{r['ref']}》")
    if args.json:
        json.dump(out, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\nJSON 已存: {args.json}")


if __name__ == "__main__":
    main()
