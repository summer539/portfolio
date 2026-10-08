#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《审核结果清单.md》：审核的第一交付物。
逐条标注 问题表现 / 法律依据 / 修改建议；必须改条款若在修订清单中有拆分项（如
第八条拆 8 项），按拆分项展开。修订清单仅作拆分数据源，不作为交付物。

用法:
  python3 scripts/build_audit_list.py --results <audit_results.json> \
      [--revision <revision_list.json>] --md <审核结果清单.md> [--doc-title 标题]
"""
import argparse, json, os

def split_items(revision, clause_id):
    """取修订清单中属于该条款的拆分项（C08-06 → C08）。"""
    if not revision:
        return []
    return [it for it in revision if it.get("clause_id", "").startswith(clause_id + "-")]


def fmt_basis(b):
    return (f"- article_id `{b['article_id']}`《{b['law_name']}》"
            f"（{b.get('doc_no') or '无文号'}）第{b['article_no']}条：{b['content']}")


def build(results_path, revision_path, title):
    data = json.load(open(results_path, encoding="utf-8"))
    results = data["results"] if isinstance(data, dict) else data
    revision = json.load(open(revision_path, encoding="utf-8")) if revision_path else None
    title = title or (data.get("document", {}).get("title") if isinstance(data, dict) else None) or "制度"

    groups = {"必须改": [], "可以不改": [], "NEED_LIBRARY_SUPPLEMENT": []}
    for r in results:
        groups.setdefault(r["result"], []).append(r)
    order = ["必须改", "可以不改", "NEED_LIBRARY_SUPPLEMENT"]

    L = [f"# 《{title}》审核结果清单", ""]
    L.append(f"- 审查条款：{len(results)} 条")
    L.append("- 审查范围：本技能内置法规库 `lawdb/law.db`（默认现行有效版本）；结论只基于库内实际返回法条")
    for k in order:
        if groups[k]:
            L.append(f"- {k}：{len(groups[k])} 条")
    L.append("")

    # ── 必须改 ──
    if groups["必须改"]:
        total_items = 0
        for r in groups["必须改"]:
            items = split_items(revision, r["clause_id"])
            total_items += max(len(items), 1)
        L += [f"## 一、必须改（{len(groups['必须改'])} 条，{total_items} 个问题点）", ""]
        for i, r in enumerate(groups["必须改"], 1):
            items = split_items(revision, r["clause_id"])
            sev = r.get("severity", "")
            L += [f"### {i}. {r['clause_label']}（{r['chapter']}）｜ 必须改{(' ｜ ' + sev) if sev else ''}", ""]
            L += ["**原文：**", "", r["original_text"], ""]
            if items:
                # 按拆分项逐项展开
                L += [f"**问题表现（{len(items)} 项）：**", ""]
                for it in items:
                    label = it.get("clause_label", it.get("clause_id", ""))
                    L += [f"- **{label}**（{it.get('error_type', '')}）：{it.get('problem', '')}", ""]
                L += ["**法律依据：**", ""]
                seen = set()
                for it in items:
                    for b in it.get("basis", []):
                        key = b["article_id"]
                        if key in seen:
                            continue
                        seen.add(key)
                        L += [fmt_basis(b), ""]
                L += ["**修改建议：**", ""]
                for it in items:
                    label = it.get("clause_label", it.get("clause_id", ""))
                    L += [f"- **{label}**：{it.get('suggestion', '')}", ""]
            else:
                if r.get("error_type"):
                    L += [f"**错误类型：** {r['error_type']}", ""]
                L += ["**问题表现：**", "", r.get("problem", ""), ""]
                if r.get("basis"):
                    L += ["**法律依据：**", ""]
                    for b in r["basis"]:
                        L += [fmt_basis(b), ""]
                if r.get("suggestion"):
                    L += ["**修改建议：**", "", r["suggestion"], ""]
            L.append("")

    # ── 可以不改 ──
    if groups["可以不改"]:
        L += [f"## 二、可以不改（{len(groups['可以不改'])} 条）", ""]
        for r in groups["可以不改"]:
            L.append(f"- **{r['clause_label']}**（{r['chapter']}）：经检索核对，现行法规下无需修改。")
        L.append("")

    # ── 待补录 ──
    if groups["NEED_LIBRARY_SUPPLEMENT"]:
        L += [f"## 三、待补录核实（{len(groups['NEED_LIBRARY_SUPPLEMENT'])} 条）", ""]
        for r in groups["NEED_LIBRARY_SUPPLEMENT"]:
            L += [f"- **{r['clause_label']}**：{r.get('problem', '')}"]
            if r.get("supplement"):
                L += [f"  - 待补充：{r['supplement']}"]
        L.append("")

    L += ["## 审查限制", "",
          "1. 本清单只使用本地法规库实际返回的法条；模型记忆或外部网页内容不作为依据。",
          "2. `NEED_LIBRARY_SUPPLEMENT` 表示当前本地证据不足或适用条件未确认，不等于违法结论。",
          "3. 修订清单（针对必须改内容的可执行修订项）在人工确认本清单后另行生成；本清单不包含修订批注。",
          ""]
    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(description="生成审核结果清单.md（第一交付物）")
    p.add_argument("--results", required=True, help="audit_results.json")
    p.add_argument("--revision", help="revision_list.json（仅作拆分数据源，可选）")
    p.add_argument("--md", required=True, help="输出 审核结果清单.md")
    p.add_argument("--doc-title", help="清单标题（缺省取 results 的 document.title）")
    args = p.parse_args()
    md = build(args.results, args.revision, args.doc_title)
    os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
    with open(args.md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"审核结果清单已生成: {args.md}（{len(md)} 字符）")


if __name__ == "__main__":
    main()
