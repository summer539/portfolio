#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doc-revision-annotate — Word 文档纯批注工具（不修改原文，仅添加批注）

用法：
    python3 add_comments.py <input.docx> <output.docx> --items items.json

JSON 清单格式（items.json）：
{
  "author": "文档修订批注助手",
  "items": [
    {"scope": "para", "para_index": 5, "comment": "批注内容"},
    {"scope": "cell", "table": 0, "row": 3, "cell": 4, "comment": "批注内容"}
  ]
}

依赖：python-docx, docx-comments
"""

import sys
import os
import json
import re
from docx import Document
from docx_comments import CommentManager, PersonInfo

DEFAULT_AUTHOR = "文档修订批注助手"


_EMOJI_RE = re.compile('[' + ''.join(
    '🔴🟡🟢🔵⚠️✅❌❓❗➕➖➗⭐ℹ️📋♻️⭕❎⬜✨💡📝📊🖍️🔄') + ']')


def strip_emojis(text):
    """移除所有 emoji 图标（Word 批注保持纯文本）"""
    return _EMOJI_RE.sub('', text)


def add_annotations(input_file, output_file, items, author=DEFAULT_AUTHOR):
    """为 DOCX 添加批注。items: [{"scope","para_index"|"table/row/cell","comment"}]"""
    doc = Document(input_file)
    mgr = CommentManager(doc)
    author_info = PersonInfo(author=author)
    paras = doc.paragraphs   # 缓存，避免循环内反复全文档扫描

    results = []
    success = 0
    fail = 0

    for idx, item in enumerate(items):
        tag = f"[{idx + 1}]"
        comment = strip_emojis(item.get("comment", ""))
        if not comment:
            results.append(f"{tag} ⚠️ 缺少 comment，跳过")
            fail += 1
            continue

        try:
            if item.get("scope", "para") == "cell":
                ti, ri, ci = item["table"], item["row"], item["cell"]
                cell = doc.tables[ti].rows[ri].cells[ci]
                # 优先锚定第一个非空段落；全空时锚定第一个段落
                target_para = None
                for p in cell.paragraphs:
                    if p.text.strip():
                        target_para = p
                        break
                if target_para is None and cell.paragraphs:
                    target_para = cell.paragraphs[0]
                if target_para is None:
                    results.append(f"{tag} ⚠️ 表{ti + 1}.R{ri + 1}.C{ci + 1} 无段落可锚定")
                    fail += 1
                    continue
                mgr.add_comment(paragraph=target_para, text=comment, author=author_info)
                results.append(f"{tag} 💬 批注 表{ti + 1}.R{ri + 1}.C{ci + 1}")
            else:
                para_idx = item["para_index"]
                if not (0 <= para_idx < len(paras)):
                    results.append(f"{tag} ⚠️ 段落索引越界: {para_idx}")
                    fail += 1
                    continue
                mgr.add_comment(paragraph=paras[para_idx], text=comment, author=author_info)
                results.append(f"{tag} 💬 批注 段落{para_idx}")
            success += 1
        except Exception as e:
            results.append(f"{tag} ❌ {e}")
            fail += 1

    doc.save(output_file)
    return results, success, fail


def main():
    if len(sys.argv) < 4 or "--items" not in sys.argv:
        print("用法: python3 add_comments.py <input.docx> <output.docx> --items items.json")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    items_path = sys.argv[sys.argv.index("--items") + 1]

    if not os.path.exists(input_file):
        print(f"错误：输入文件不存在 {input_file}")
        sys.exit(1)

    with open(items_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    author = data.get("author", DEFAULT_AUTHOR)
    items = data.get("items", data if isinstance(data, list) else [])

    results, success, fail = add_annotations(input_file, output_file, items, author)

    print(f"批注完成！输出文件: {output_file}")
    print(f"作者署名: {author}")
    print(f"统计: 成功 {success} 条 / 失败 {fail} 条")
    print("-" * 50)
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
