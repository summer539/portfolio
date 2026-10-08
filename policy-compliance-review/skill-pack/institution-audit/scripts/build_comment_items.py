#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_comment_items.py — 从 revision_list.json 生成 doc-revision-annotate 批注文本
（四段式人话版：【修改】headline / 【修订依据】basis_human / 【修订建议】suggestion / 【修订性质】结构化块）

背景（2026-08-27 用户定稿）：
- 批注四段用 \n 真换行分隔（revision_edit.py 的 _split_comment_newlines 自动转 w:br）
- 批注中不含 article_id（可读性优先；可追溯性由修订清单.md / revision_list.json 承担）
- 【修改】= 问题+怎么办，不带条款位置、不带"类型X"编号；标签随修订性质变化（【新增】/【删除】）
- 【修订性质】末段为**结构化信息**（供前端解析展示，非阅读用途）：
    修改 → "修改\n{原始}：<min_original>\n{修改}：<min_modified>"
    新增 → "新增\n{新增}：<min_modified>"
    删除 → "删除\n{删除}：<min_original>"
  缺省（旧数据无 revision_type）→ 回退 "修改"，不输出 {原始}/{修改} 行。

用法：
    python3 build_comment_items.py --revision <revision_list.json> --items <items.json>
    # 默认清理 article_id；--keep-aid 保留；--dry-run 只打印不写文件

items.json 匹配规则（按优先级）：
    1. item 含 clause_id（如 "C08-13"）→ 精确匹配 revision.clause_id
    2. item.clause 文本（如 "第八条第（十三）项"）→ clause_label 精确匹配
    3. item.clause 文本前缀匹配 clause_label（如 "第三条第2款" → "第三条"）
    匹配失败则跳过并告警（不覆盖原 comment）。

坑（已踩过，勿重犯）：
    ① 去 article_id 后必须清空括号：while "（）" in s: s = s.replace("（）", "")
    ② 嵌套场景（文号，article_id=…，现行有效）：先删 "[,，]?\s*article_id=\d+(?:/\d+)*"
       片段（保留"现行有效"），再兜底删整括号、清空括号
"""
import argparse
import json
import re
import sys


def strip_aid(s: str) -> str:
    """从批注文本中清除 article_id，保留可读性。"""
    s = re.sub(r"[,，]?\s*article_id=\d+(?:/\d+)*", "", s)   # 删 article_id=… 片段（含前导逗号）
    s = re.sub(r"（[^）]*?article_id[^）]*）", "", s)          # 兜底：整括号含 article_id 则删除
    while "（）" in s:                                         # 坑①：清残留空括号
        s = s.replace("（）", "")
    s = s.replace("（，", "（").replace("，）", "）")
    return s


def match_revision(item, revisions):
    """按优先级把 item 匹配到 revision 对象。"""
    if item.get("clause_id"):
        for r in revisions:
            if r["clause_id"] == item["clause_id"]:
                return r
    clause = item.get("clause", "")
    if not clause:
        return None
    for r in revisions:                                       # 精确
        if r.get("clause_label") == clause:
            return r
    for r in revisions:                                       # 前缀（坑：第三条第2款 → 第三条）
        if clause.startswith(r.get("clause_label", "")) and r.get("clause_label"):
            return r
    return None


def infer_revision_type(r):
    """修订性质推断：revision_type 缺失时按 old/new（或 min 字段）判定。"""
    rt = r.get("revision_type")
    if rt:
        return rt
    old = r.get("old") or r.get("min_original")
    new = r.get("new") or r.get("min_modified")
    if old and new:
        return "修改"
    if new and not old:
        return "新增"
    if old and not new:
        return "删除"
    return "修改"


def build_comment(r, keep_aid: bool) -> str:
    """四段式批注：【修改】/【修订依据】/【修订建议】/【修订性质】（结构化，供前端解析）。"""
    rtype = infer_revision_type(r)
    headline = r.get("headline") or r.get("error_type", "")
    basis = r.get("basis_human") or ""
    if isinstance(basis, list):                            # 兼容列表式 basis_human（逐条转述）
        basis = "\n".join(f"{i}. {line}" for i, line in enumerate(basis, 1))
    if not keep_aid:
        basis = strip_aid(basis)
    suggestion = r.get("suggestion", "")

    # 【修订性质】结构化块：第一行=性质枚举，其后为 {键}：值 行（前端按行解析）
    if rtype == "新增":
        prop = f"新增\n{{新增}}：{r.get('min_modified', r.get('min_original', ''))}"
    elif rtype == "删除":
        prop = f"删除\n{{删除}}：{r.get('min_original', '')}"
    else:
        prop = "修改"
        if r.get("min_original") or r.get("min_modified"):
            prop += f"\n{{原始}}：{r.get('min_original', '')}\n{{修改}}：{r.get('min_modified', '')}"

    return (f"【{rtype}】{headline}\n"
            f"【修订依据】{basis}\n"
            f"【修订建议】{suggestion}\n"
            f"【修订性质】{prop}")


def main():
    ap = argparse.ArgumentParser(description="从 revision_list.json 生成批注三段式 comment")
    ap.add_argument("--revision", required=True, help="revision_list.json 路径")
    ap.add_argument("--items", required=True, help="doc-revision-annotate items.json 路径（就地更新 comment）")
    ap.add_argument("--keep-aid", action="store_true", help="保留 article_id（默认清理）")
    ap.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    args = ap.parse_args()

    revisions = json.load(open(args.revision, encoding="utf-8"))
    data = json.load(open(args.items, encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) and "items" in data else data

    ok, skip = 0, []
    for it in items:
        r = match_revision(it, revisions)
        if r is None:
            skip.append(it.get("clause") or it.get("clause_id") or "?")
            continue
        it["comment"] = build_comment(r, args.keep_aid)
        ok += 1

    if skip:
        print(f"⚠️ 未匹配 {len(skip)} 条（comment 未改动）: {skip}")
    if not args.dry_run:
        json.dump(data, open(args.items, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✅ 已更新 {ok} 条 comment（四段式，\\n 分隔；article_id {'保留' if args.keep_aid else '已清理'}）")
    if args.dry_run:
        for it in items:
            print("----", it.get("clause"), "\n", it.get("comment", "")[:120])


if __name__ == "__main__":
    sys.exit(main())
