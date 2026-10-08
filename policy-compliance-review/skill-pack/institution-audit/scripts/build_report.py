#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将制度结构化结果与审核结果组装为 JSON 和 Markdown 报告。"""
import argparse, json, os

def build_md(doc, results):
    total = len(results)
    counts = {}
    for r in results: counts[r["result"]] = counts.get(r["result"], 0) + 1
    lines = [f"# {doc['title']} 合规审查报告", "", f"- 审查文件：`{doc['source']}`", "- 审查范围：本技能内置法规库 `lawdb/law.db`，默认现行有效版本", "- 审查条款：%d 条" % total, "", "## 审查概况", ""]
    for k in ("可以不改", "必须改", "NEED_LIBRARY_SUPPLEMENT"):
        lines.append(f"- {k}：{counts.get(k, 0)} 条")
    lines += ["", "## 审查结论", ""]
    for r in results:
        lines += [f"### {r['clause_label']}（{r['chapter']}）", "", f"**原文：** {r['original_text']}", "", f"**结论：** `{r['result']}`"]
        if r.get("error_type"): lines += [f"", f"**错误类型：** {r['error_type']}"]
        if r.get("problem"): lines += [f"", f"**问题：** {r['problem']}"]
        if r.get("basis"): lines += ["", "**依据：**"] + [f"- article_id `{b['article_id']}`，《{b['law_name']}》第{b['article_no']}条：{b['content']}" for b in r["basis"]]
        if r.get("suggestion"): lines += ["", f"**建议修改：** {r['suggestion']}"]
        if r.get("supplement"): lines += ["", f"**待补充信息：** {r['supplement']}"]
        lines.append("")
    lines += ["## 审查限制", "", "1. 本报告只使用本地法规库实际返回的法条；没有把模型记忆或外部网页内容作为依据。", "2. `NEED_LIBRARY_SUPPLEMENT` 表示当前本地证据不足或适用条件未确认，不等于违法结论。", "3. 企业内部制度之间的一致性、CMMI 合规性和公司内部安全标准，尚未接入内部制度库，不能在本报告中替代国家法规判断。"]
    return "\n".join(lines) + "\n"

def main():
    p=argparse.ArgumentParser(); p.add_argument("--document", required=True); p.add_argument("--results", required=True); p.add_argument("--json", required=True); p.add_argument("--md", required=True); args=p.parse_args()
    doc=json.load(open(args.document,encoding="utf-8")); results=json.load(open(args.results,encoding="utf-8"))
    out={"document":doc,"results":results,"summary":{}}
    for r in results: out["summary"][r["result"]]=out["summary"].get(r["result"],0)+1
    os.makedirs(os.path.dirname(os.path.abspath(args.json)),exist_ok=True)
    with open(args.json,"w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
    with open(args.md,"w",encoding="utf-8") as f: f.write(build_md(doc,results))
    print(f"报告已生成: {args.json} / {args.md}")
if __name__ == "__main__": main()
