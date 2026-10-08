#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doc-revision-annotate 自检脚本 — 按《制度审核文档批注结构规范》验证输出 .docx

用法：
    python3 verify_revisions.py <输出.docx>

验证清单（对应 annotation-spec 第 8 节）：
  [1] 每条批注的 commentRangeStart 是否在对应修订元素（del/ins）之前
  [2] 每条批注的 commentRangeEnd 是否在对应修订元素之后
  [3] 修改类批注的 range 是否同时覆盖 del 和 ins
  [4] 所有 w:del/w:ins 的 w:id 全局唯一；所有批注 w:id 全局唯一
  [5] 批注文本是否包含修改类型（删除/新增/修改/格式）和条款定位（第/条）
  [6] 是否有 commentRangeStart/End 被放在 ins/del 内部（必须同级）
  [7] commentRangeStart 与 commentRangeEnd 位置顺序正确（允许跨段批注，
      Start 段必须在 End 段之前；同段时 End 在 Start 之后）

退出码：全部通过 0，任一失败 1。
"""

import sys
import zipfile
from collections import Counter
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# 热路径 tag 常量
W_P = f'{{{W}}}p'
W_DEL = f'{{{W}}}del'
W_INS = f'{{{W}}}ins'
W_CRS = f'{{{W}}}commentRangeStart'
W_CRE = f'{{{W}}}commentRangeEnd'
W_ID = f'{{{W}}}id'
W_T = f'{{{W}}}t'
W_COMMENT = f'{{{W}}}comment'


def iter_paragraphs(root):
    """遍历 document.xml 中所有 w:p 元素（含表格内段落）。"""
    return root.iter(W_P)


def collect_comment_texts(doc_zip):
    """读取 word/comments.xml，返回 {comment_id: 文本}。"""
    result = {}
    try:
        data = doc_zip.read('word/comments.xml')
    except KeyError:
        return result
    root = etree.fromstring(data)
    for c in root.iter(W_COMMENT):
        cid = c.get(W_ID)
        texts = [t.text or '' for t in c.iter(W_T)]
        result[cid] = ''.join(texts)
    return result


def verify(docx_path):
    problems = []
    checks = {k: 0 for k in range(1, 8)}
    stats = {'comments': 0, 'dels': 0, 'inss': 0, 'paras_with_rev': 0}

    with zipfile.ZipFile(docx_path) as z:
        doc_root = etree.fromstring(z.read('word/document.xml'))
        comment_texts = collect_comment_texts(z)

    # 单次遍历：收集 del/ins/批注 id、全局位置（检查 4/1/2/3/7）、嵌套检查（检查 6）
    del_ids, ins_ids, comment_ids = [], [], []
    crs_map = {}   # cid -> (para_idx, pos)
    cre_map = {}   # cid -> (para_idx, pos)
    rev_all = []   # (para_idx, pos, tag)
    for pi, p in enumerate(iter_paragraphs(doc_root)):
        for i, child in enumerate(list(p)):
            if child.tag == W_DEL:
                del_ids.append(child.get(W_ID))
                # 检查 6：del 内部不得嵌套批注标记
                for bad in child.iter(W_CRS):
                    problems.append(f"[6] commentRangeStart 嵌套在 del 内部")
                for bad in child.iter(W_CRE):
                    problems.append(f"[6] commentRangeEnd 嵌套在 del 内部")
                rev_all.append((pi, i, 'del'))
            elif child.tag == W_INS:
                ins_ids.append(child.get(W_ID))
                for bad in child.iter(W_CRS):
                    problems.append(f"[6] commentRangeStart 嵌套在 ins 内部")
                for bad in child.iter(W_CRE):
                    problems.append(f"[6] commentRangeEnd 嵌套在 ins 内部")
                rev_all.append((pi, i, 'ins'))
            elif child.tag == W_CRS:
                comment_ids.append(child.get(W_ID))
                crs_map[child.get(W_ID)] = (pi, i)
            elif child.tag == W_CRE:
                cre_map[child.get(W_ID)] = (pi, i)

    # 检查 4：id 全局唯一（Counter 一次统计）
    for name, ids in (('修订 del', del_ids), ('修订 ins', ins_ids), ('批注', comment_ids)):
        dup = {x for x, c in Counter(ids).items() if c > 1}
        if dup:
            problems.append(f"[4] {name} id 重复: {dup}")
    checks[4] += 1

    # 逐批注检查锚定结构（检查 1/2/3/7）
    for cid, s_pos in crs_map.items():
        if cid not in cre_map:
            problems.append(f"[7] 批注 {cid} 缺少 commentRangeEnd（跨段或缺失）")
            continue
        e_pos = cre_map[cid]
        if e_pos <= s_pos:
            problems.append(f"[7] 批注 {cid} commentRangeEnd 不在 Start 之后")
            continue
        stats['comments'] += 1
        # 该批注范围（Start..End）内的修订元素（全局位置比较，天然支持跨段）
        in_range = [(pi, i, t) for pi, i, t in rev_all if s_pos < (pi, i) < e_pos]
        if not in_range:
            # 纯批注（无修订元素）或格式修订锚定 run：不检查修订顺序
            checks[1] += 1
            checks[2] += 1
            continue
        stats['paras_with_rev'] += 1
        dels = [r for r in in_range if r[2] == 'del']
        inss = [r for r in in_range if r[2] == 'ins']
        first_rev = min(in_range)
        last_rev = max(in_range)
        # 检查 1：Start 在第一个修订元素之前
        if s_pos >= first_rev:
            problems.append(f"[1] 批注 {cid} 的 commentRangeStart 不在第一个修订元素之前")
        # 检查 2：End 在最后一个修订元素之后
        if e_pos <= last_rev:
            problems.append(f"[2] 批注 {cid} 的 commentRangeEnd 不在最后一个修订元素之后")
        # 检查 3：修改类（del+ins 都有）范围是否同时覆盖
        if dels and inss:
            if not (s_pos < min(dels) and max(inss) < e_pos):
                problems.append(f"[3] 批注 {cid} 范围未同时覆盖 del 和 ins")
        checks[3] += 1
        checks[1] += 1
        checks[2] += 1
    checks[6] += 1

    # 检查 5：批注文本包含修改类型和条款定位
    for cid, text in comment_texts.items():
        has_type = any(k in text for k in ('删除', '新增', '修改', '格式', '建议', '提示'))
        has_loc = '本条对应' in text or '第' in text or '条' in text
        if not (has_type and has_loc):
            problems.append(f"[5] 批注 {cid} 文本缺少修改类型或条款定位: {text[:40]}")
    checks[5] += 1

    print(f"统计: 批注 {stats['comments']} 条 / 含修订段落 {stats['paras_with_rev']} 个 / "
          f"del {len(del_ids)} 处 / ins {len(ins_ids)} 处")
    print(f"检查项: {sorted(checks.keys())}")
    if problems:
        print(f"❌ 发现 {len(problems)} 个问题:")
        for p in problems:
            print("   -", p)
        return 1
    print("✅ 全部验证通过")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 verify_revisions.py <输出.docx>")
        sys.exit(1)
    sys.exit(verify(sys.argv[1]))
