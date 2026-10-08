#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx 全文提取标准工具（XML 级，含 w:sdt 内容控件）

用途：原生 docx 模板（某化工集团格式合同）的填写值多存于 w:sdt 内容控件，
python-docx 标准 API（cell.text / paragraph.text）不解析 sdt 内文本，
会把已填写内容误判为空白（2026-09-03 事故教训：塑封套框架合同审核误判
"首部全部空白"）。解析 docx 前必须先统计 sdt 数：
  python3 -c "import zipfile;print(zipfile.ZipFile('x.docx').read('word/document.xml').decode('utf-8').count('<w:sdt>'))"
sdt > 0 时一律用本脚本提取（段落+表格按文档顺序，含 sdt 嵌套文本）。

用法：
  python3 xml_extract.py <input.docx> [output.txt]
  （不传 output.txt 时输出到 <input 同名>.txt 所在目录）

依赖：lxml（pip install lxml）
"""
import zipfile, sys, os
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}

def elem_text(el):
    """元素内全部 w:t 文本（含 sdt 内嵌套）"""
    return "".join(el.xpath('.//w:t/text()', namespaces=NS))

def para_text(p):
    """段落文本：按文档顺序取全部 w:t（含 sdt 内）"""
    return "".join((node.text or "") for node in p.iter() if node.tag == f'{{{W}}}t')

def block_children(container):
    """展开容器的块级子元素：w:p / w:tbl，并递归展开块级 w:sdt
    （2026-09-03 二次事故教训：模板正文可能整体包在顶层 sdt 内容控件内，
    只遍历直接子元素会漏读 sdt 包裹的整块条款，曾致"条款7→15跳号"误报）"""
    blocks = []
    for child in container:
        tag = etree.QName(child).localname
        if tag == 'sdt':
            sc = child.find(f'{{{W}}}sdtContent')
            if sc is not None:
                blocks.extend(block_children(sc))
        elif tag in ('p', 'tbl'):
            blocks.append(child)
    return blocks

def extract(path):
    z = zipfile.ZipFile(path)
    doc = z.read("word/document.xml")
    root = etree.fromstring(doc)
    body = root.find(f'{{{W}}}body')
    out, ti = [], 0
    for child in block_children(body):
        if child.tag == f'{{{W}}}p':
            t = para_text(child).strip()
            if t:
                out.append(t)
        elif child.tag == f'{{{W}}}tbl':
            ti += 1
            out.append(f"--- 表格{ti} ---")
            seen_rows = set()
            for tr in child.findall(f'{{{W}}}tr'):
                cells = []
                for tc in tr.findall(f'{{{W}}}tc'):
                    cells.append(" ".join(elem_text(tc).split()))
                dedup, prev = [], None
                for ct in cells:
                    if ct != prev:
                        dedup.append(ct)
                    prev = ct
                line = " | ".join(dedup).strip(" |")
                if line and line not in seen_rows:
                    seen_rows.add(line)
                    out.append(line)
    sdt_n = doc.decode('utf-8').count('<w:sdt>')
    return "\n".join(out), sdt_n

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + "_full.txt"
    txt, sdt_n = extract(src)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"sdt数: {sdt_n} | 提取完成: {dst} | 行数: {len(txt.splitlines())}")
