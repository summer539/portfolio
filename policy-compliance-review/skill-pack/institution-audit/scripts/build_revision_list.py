#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《修订清单.md》：人工确认审核结果清单后，针对"必须改"内容输出。
格式按 rules/revision_output_format.md 三段式：【修改】/【修订依据】/【修订建议】。

用法:
  python3 scripts/build_revision_list.py --revision <revision_list.json> \
      --md <修订清单.md> --doc-title <制度全称>
"""
import argparse, json, os, re

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
          "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
          "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
          "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
          "二十六": 26, "二十七": 27, "二十八": 28, "二十九": 29, "三十": 30}


def sort_key(it):
    m = re.match(r"第([一二三四五六七八九十]+)条", it.get("clause_label", ""))
    art = CN_NUM.get(m.group(1), 99) if m else 99
    m2 = re.search(r"（([一二三四五六七八九十]+)）", it.get("clause_label", ""))
    item = CN_NUM.get(m2.group(1), 0) if m2 else 0
    return (art, item)


def infer_revision_type(it):
    """修订性质推断：revision_type 缺失时按 old/new（或 min 字段）判定。"""
    rt = it.get("revision_type")
    if rt:
        return rt
    old = it.get("old") or it.get("min_original")
    new = it.get("new") or it.get("min_modified")
    if old and new:
        return "修改"
    if new and not old:
        return "新增"
    if old and not new:
        return "删除"
    return "修改"


def fmt_basis(b, idx):
    status = b.get("status", "")
    tag = "（已废止，仅作背景说明）" if status == "已废止" else ""
    return (f"{idx}. 《{b['law_name']}》（{b.get('doc_no') or '无文号'}）"
            f"第{b['article_no']}条（article_id={b['article_id']}）{tag}："
            f"“{b['content']}”")


def build(revision_path, title):
    items = json.load(open(revision_path, encoding="utf-8"))
    items = sorted(items, key=sort_key)

    L = [f"# 《{title}》修订清单", "",
         f"- 生成依据：审核结果清单（人工确认后）| 修订项：{len(items)} 项（仅针对必须改内容）",
         "- 定位键：clause_id + 项号（如 C08-13），供修订技能逐条消费", ""]

    for i, it in enumerate(items, 1):
        rtype = infer_revision_type(it)
        L += [f"## {i}. {it['clause_label']}", "",
              f"**【{rtype}】**{it.get('headline') or it.get('error_type', '')}", ""]
        # 修订性质（修改/新增/删除）＋最小修订范围对比（始终输出；无 min 字段时仅性质枚举）
        L += [f"**【修订性质】**{rtype}", ""]
        if rtype == "修改":
            if it.get("min_original") is not None or it.get("min_modified") is not None:
                L += [f"{{原始}}：{it.get('min_original','')}", f"{{修改}}：{it.get('min_modified','')}", ""]
        elif rtype == "新增":
            L += [f"{{新增}}：{it.get('min_modified', it.get('min_original',''))}", ""]
        elif rtype == "删除":
            L += [f"{{删除}}：{it.get('min_original','')}", ""]
        if it.get("basis_human"):
            # 人话版依据（审核员撰写）：直接呈现（列表逐条展开为编号行）
            L += ["**【修订依据】**", ""]
            bh = it["basis_human"]
            if isinstance(bh, list):
                for k, line in enumerate(bh, 1):
                    L += [f"{k}. {line}", ""]
            else:
                L += [bh, ""]
        else:
            L += ["**【修订依据】**", ""]
            # 现行有效在前，已废止作背景说明放后
            basis = sorted(it.get("basis", []), key=lambda b: 0 if b.get("status") != "已废止" else 1)
            for j, b in enumerate(basis, 1):
                L += [fmt_basis(b, j), ""]
        L += ["**【修订建议】**", "", it.get("suggestion", ""), "", ""]

    # 依据核验说明
    L += ["## 依据核验说明", "", "| 依据 | 本地库状态 |", "|---|---|"]
    seen = set()
    for it in items:
        for b in it.get("basis", []):
            key = b["article_id"]
            if key in seen:
                continue
            seen.add(key)
            st = "✅ 已入库（现行有效）" if b.get("status") != "已废止" else "✅ 已入库（已废止，仅作背景）"
            L.append(f"| 《{b['law_name']}》第{b['article_no']}条（article_id={key}） | {st} |")
    L += ["", "> 说明：已废止法规不作为修订依据，仅用于证明制度所引标准已失效。"]
    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(description="生成修订清单.md（人工确认审核结果清单后交付）")
    p.add_argument("--revision", required=True, help="revision_list.json")
    p.add_argument("--md", required=True, help="输出 修订清单.md")
    p.add_argument("--doc-title", required=True, help="制度全称")
    p.add_argument("--no-writeback", action="store_true",
                   help="不把推断的 revision_type/min_original/min_modified 写回 revision_list.json")
    args = p.parse_args()

    # 推断修订性质并写回（保证修订清单.md 与后续批注环节字段一致）
    items = json.load(open(args.revision, encoding="utf-8"))
    changed = 0
    for it in items:
        rt = infer_revision_type(it)
        if it.get("revision_type") != rt:
            it["revision_type"] = rt
            changed += 1
        # 最小范围字段兜底：修改→difflib 计算；删除→min_original=old；新增→min_modified=new
        if rt == "修改" and "min_original" not in it and "min_modified" not in it:
            if it.get("old") or it.get("new"):
                import difflib
                old, new = it.get("old", ""), it.get("new", "")
                sm = difflib.SequenceMatcher(None, old, new)
                dels, inss = [], []
                for tag, i1, i2, j1, j2 in sm.get_opcodes():
                    if tag == "delete":
                        dels.append(old[i1:i2])
                    elif tag == "insert":
                        inss.append(new[j1:j2])
                    elif tag == "replace":
                        dels.append(old[i1:i2]); inss.append(new[j1:j2])
                it["min_original"], it["min_modified"] = "".join(dels), "".join(inss)
                changed += 1
        elif rt == "删除" and "min_original" not in it and it.get("old"):
            it["min_original"] = it["old"]
            changed += 1
        elif rt == "新增" and "min_modified" not in it and it.get("new"):
            it["min_modified"] = it["new"]
            changed += 1
    if changed and not args.no_writeback:
        with open(args.revision, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        print(f"ℹ️ 已写回 revision_list.json：补齐 {changed} 处修订性质/最小范围字段")

    md = build(args.revision, args.doc_title)
    os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
    with open(args.md, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"修订清单已生成: {args.md}（{len(md)} 字符，{len(items)} 项）")


if __name__ == "__main__":
    main()
