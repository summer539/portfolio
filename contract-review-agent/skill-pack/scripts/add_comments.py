#!/usr/bin/env python3
"""
合同审核批注工具 - 为Word DOCX文档添加审核批注

用途：对合同审核结果以Word批注形式标注到文档中
依赖：python-docx, docx-comments
用法：
    python3 add_comments.py <input.docx> <output.docx> [--annotations ANNOTATIONS.json]
"""

import json
import sys
import argparse
from typing import Dict, List, Tuple, Optional
from docx import Document
from docx_comments import CommentManager, PersonInfo
from docx.shared import RGBColor


SEVERITY_MARKS = {
    "risk": "⚠️ 风险",
    "suggest": "💡 建议",
    "confirm": "❓ 待确认",
    "info": "ℹ️ 提示",
}


def add_annotations(
    input_file: str,
    output_file: str,
    annotations: Dict[int, Tuple[str, str]],
    author_name: str = "小龙(合同审核助手)",
) -> Tuple[int, int]:
    """
    为 DOCX 文件添加审核批注。

    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        annotations: {段落索引: (批注内容, 严重级别)} 的字典
                     严重级别: "risk" | "suggest" | "confirm" | "info"
        author_name: 批注作者名

    Returns:
        (成功数, 失败数)
    """
    doc = Document(input_file)
    mgr = CommentManager(doc)
    author = PersonInfo(author=author_name)

    success = 0
    fail = 0

    for para_idx, (comment_text, severity) in annotations.items():
        try:
            if para_idx < len(doc.paragraphs):
                para = doc.paragraphs[para_idx]
                if para.text.strip():
                    # 格式化批注内容：添加严重级别标记
                    mark = SEVERITY_MARKS.get(severity, "📝")
                    full_text = f"[{mark}] {comment_text}"

                    mgr.add_comment(
                        paragraph=para,
                        text=full_text,
                        author=author,
                    )
                    # 给有风险的段落添加红色下划线标记
                    if severity == "risk":
                        for run in para.runs:
                            run.font.color.rgb = RGBColor(200, 30, 30)
                    elif severity == "confirm":
                        for run in para.runs:
                            run.font.color.rgb = RGBColor(200, 130, 0)
                    success += 1
                else:
                    fail += 1
            else:
                fail += 1
        except Exception as e:
            print(f"段落 {para_idx} 添加失败: {e}", file=sys.stderr)
            fail += 1

    doc.save(output_file)
    return success, fail


def parse_annotations_json(json_path: str) -> Dict[int, Tuple[str, str]]:
    """从 JSON 文件解析批注配置。"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = {}
    for item in data:
        if "paragraph" in item and "text" in item:
            para_idx = item["paragraph"]
            text = item["text"]
            severity = item.get("severity", "info")
            result[para_idx] = (text, severity)
    return result


def auto_detect_contract_position(doc: Document) -> str:
    """
    自动检测合同立场（甲方/乙方）。
    通过关键词匹配粗略判断。
    """
    text_lower = " ".join([p.text for p in doc.paragraphs if p.text.strip()]).lower()

    seller_keywords = ["卖方", "供应商", "供方", "乙方", "出卖人", "销售方", "服务方"]
    buyer_keywords = ["买方", "采购方", "需方", "甲方", "买受人", "购买方"]

    seller_score = sum(1 for kw in seller_keywords if kw in text_lower)
    buyer_score = sum(1 for kw in buyer_keywords if kw in text_lower)

    if seller_score > buyer_score:
        return "乙方立场（我方是供应商）"
    elif buyer_score > seller_score:
        return "甲方立场（我方是采购方）"
    else:
        return "中立/未确定"


def main():
    parser = argparse.ArgumentParser(
        description="合同审核批注工具 - 为Word文档添加审核批注"
    )
    parser.add_argument("input", help="输入 DOCX 文件路径")
    parser.add_argument("output", help="输出 DOCX 文件路径")
    parser.add_argument(
        "--annotations", "-a",
        help="批注JSON文件路径，格式：[{\"paragraph\": 0, \"text\": \"内容\", \"severity\": \"risk\"}]",
    )
    parser.add_argument(
        "--author", default="小龙(合同审核助手)",
        help="批注作者名 (默认: 小龙(合同审核助手))",
    )
    parser.add_argument(
        "--detect-position", action="store_true",
        help="自动检测合同立场并输出",
    )

    args = parser.parse_args()

    if args.detect_position:
        doc = Document(args.input)
        position = auto_detect_contract_position(doc)
        print(f"检测结果: {position}")
        return

    if not args.annotations:
        print("错误: 请提供批注JSON文件 (--annotations)", file=sys.stderr)
        sys.exit(1)

    annotations = parse_annotations_json(args.annotations)
    success, fail = add_annotations(
        args.input, args.output, annotations, args.author
    )

    print(f"审核完成！成功添加 {success} 条批注", end="")
    if fail > 0:
        print(f"，{fail} 条跳过（空段落或索引越界）", end="")
    print(f"")
    print(f"输出文件: {args.output}")


if __name__ == "__main__":
    main()