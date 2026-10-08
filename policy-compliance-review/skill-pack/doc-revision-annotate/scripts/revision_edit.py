#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doc-revision-annotate 核心脚本 — Word 文档修订标记 + 批注（WPS/Word 双兼容）

核心流程（严格两阶段）：
    阶段 1 修订：先用 lxml 在 XML 层生成修订标记（w:del / w:ins / 格式修订），
                并记录本次修订生成的全部 DEL/INS 的 w:id。
    阶段 2 批注：修订全部完成后，用 docx_comments 创建批注内容（含 WPS 必需
                的全部基础设施部件），再按 w:id 把 commentRangeStart/End/Reference
                精确定位到对应修订元素上（元素引用会失效、文本定位不可靠，只有
                w:id 在段落重建后依然稳定）。

修订精度（用户强制，2026-08-25/26 固化）：
    - replace 自动最小化拆分：新旧文本最长公共子串（≥2 字符）保留不删不加，
      差异部分「先 DEL 后 INS」，禁止出现「多删除又补回来」的视觉混乱。
    - 增加用 insert（锚点后插入，原文零删除）；删除用 delete（仅 DEL）。
    - 格式修订用 action=format：只改格式不动文字，通过 w:rPrChange / w:pPrChange
      属性层可追踪变更实现，绝不用 replace 把格式问题当内容改。

批注锚定规则（按 w:id，2026-08-26 固化）：
    - 修改 replace（DEL+INS）：范围 = 第一个修订元素前 → 最后一个修订元素后
      （按文档顺序取首尾，DEL 不必然在 INS 前，见坑 ③）
    - 增加 insert：范围 = INS 前 → INS 后（精确覆盖插入内容）
    - 删除 delete：范围 = 第一个 DEL 前 → 最后一个 DEL 后
    - 位置铁律：commentRangeStart 在第一个修订元素之前、commentRangeEnd 在
      最后一个修订元素之后，同段落、同级（直接子元素层），不跨段不嵌套。
    - 修订类批注自动追加「本条对应第X条的删除+新增 / 删除 / 新增 / 格式修订」，
      X 优先取 item.clause / item.条款号，否则为清单条目序号 idx+1。

WPS 兼容性关键：
    - WPS 显示批注依赖 docx_comments 创建的 4 个部件：
      comments.xml / commentsExtended.xml / commentsIds.xml / commentsExtensible.xml
      只手工写 comments.xml 时 WPS 不显示批注（Word 正常）
    - 修订时间使用 +08:00 时区格式、w14:paraId/textId、mc:Ignorable 等
      与 WPS 原生输出一致的属性
    - 修订 id 从 10000 起，避免与文档已有修订冲突

用法：
    python3 revision_edit.py <input.docx> <output.docx> --items items.json

JSON 修改清单格式（items.json）：
{
  "author": "文档修订批注助手",              // 可选，默认"文档修订批注助手"
  "items": [
    {
      "action": "replace",                  // replace | delete | insert | format
      "scope": "cell",                      // para | cell
      "table": 0, "row": 3, "cell": 4,      // scope=cell 时必填（0 起始）
      "para_index": 5,                      // scope=para 时必填（0 起始）
      "old": "原文",                        // replace/delete 必填
      "new": "新文本",                      // replace/insert 必填
      "anchor": "锚点文本",                 // insert 必填：在该文本之后插入 new
      "level": "run",                       // format 必填：run（字符格式）| para（段落格式）
      "run_text": "文本",                   // format level=run 可选：仅改该文本所在 run
      "new_format": {"bold": true},         // format 必填：语义键值对（见下）
      "clause": "第十三条",                 // 可选：条款定位，用于批注文本标注
      "comment": "批注内容（可选）",         // 有值则添加批注
      "comment_only": false                 // true: 仅加批注，不做修订
    }
  ],
  "merge_by_clause": false                 // 可选：true 时按 clause 合并批注（一条款一条批注）；
                                           // 默认 false：每个清单条目（item）一条独立批注，逐条不合并
}

new_format 键值表：
    字符格式（level=run）：
      bold: bool | italic: bool | underline: bool | font: str |
      font_size_pt: number | color: "RRGGBB"
    段落格式（level=para）：
      align: "left|center|right|both|distribute" |
      line_spacing: number（倍数）| first_line_indent_pt: number
    false/None 表示移除该格式。

依赖：python-docx, docx-comments, lxml
"""

import sys
import os
import json
import re
import copy
from collections import Counter
from datetime import datetime, timezone, timedelta
from lxml import etree
from docx import Document
from docx_comments import CommentManager, PersonInfo

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
DEFAULT_AUTHOR = "文档修订批注助手"
REV_ID = [10000]          # 修订 id 从 10000 起，避开文档已有修订
CST = timezone(timedelta(hours=8))
MIN_COMMON_LEN = 2        # replace 最小化拆分：公共块最短保留长度
LCS_LIMIT = 4_000_000     # 超长文本降级阈值（m×n）

# 热路径 tag 常量（避免每次 split 取 local_name）
W_R = f'{{{W}}}r'
W_INS = f'{{{W}}}ins'
W_DEL = f'{{{W}}}del'
W_T = f'{{{W}}}t'
W_DELTEXT = f'{{{W}}}delText'
W_BR = f'{{{W}}}br'
W_TAB = f'{{{W}}}tab'
W_RPR = f'{{{W}}}rPr'
W_RSTYLE = f'{{{W}}}rStyle'
W_ID = f'{{{W}}}id'
W_CRS = f'{{{W}}}commentRangeStart'
W_CRE = f'{{{W}}}commentRangeEnd'
W_CREF = f'{{{W}}}commentReference'
W_BR = f'{{{W}}}br'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'


def _split_comment_newlines(mgr, cid):
    """把批注文本中的 \\n 转为 w:br 真换行。

    docx_comments 的 add_comment 把整段文本塞进单个 w:t，\\n 不会显示为换行；
    此处按 id 找到刚创建的 comment，将 w:t 按 \\n 拆为 w:t + w:br + w:t 序列。
    """
    root = mgr._comments_xml
    for c in root.findall(f'{{{W}}}comment'):
        if c.get(f'{{{W}}}id') != str(cid):
            continue
        for p in c.findall(f'{{{W}}}p'):
            for r in p.findall(f'{{{W}}}r'):
                for t in r.findall(f'{{{W}}}t'):
                    if t.text and '\n' in t.text:
                        parts = t.text.split('\n')
                        t.text = parts[0]
                        parent = t.getparent()
                        idx = list(parent).index(t)
                        for seg in parts[1:]:
                            br = etree.Element(W_BR)
                            parent.insert(idx + 1, br)
                            idx += 1
                            nt = etree.Element(f'{{{W}}}t')
                            nt.text = seg
                            if t.get(XML_SPACE) == 'preserve':
                                nt.set(XML_SPACE, 'preserve')
                            parent.insert(idx + 1, nt)
                            idx += 1
        break
    mgr._save_comments()
W_P = f'{{{W}}}p'

# emoji 清理：预编译字符类正则（原循环 replace 改为单次 sub）
_EMOJI_RE = re.compile('[' + ''.join(
    '🔴🟡🟢🔵⚠️✅❌❓❗➕➖➗⭐ℹ️📋♻️⭕❎⬜✨💡📝📊🖍️🔄') + ']')

# 修订时间戳缓存：同一次运行内（60 秒窗口）复用，避免数百次 strftime
_now_cache = {'t': None, 'ts': ''}


def next_id():
    REV_ID[0] += 1
    return REV_ID[0]


def now_str():
    now = _now_cache['t']
    ts = _now_cache['ts']
    if now is None or (datetime.now(CST) - now).total_seconds() >= 60:
        ts = datetime.now(CST).strftime('%Y-%m-%dT%H:%M:%S+08:00')
        _now_cache['t'] = datetime.now(CST)
        _now_cache['ts'] = ts
    return ts


def strip_emojis(text):
    """移除所有 emoji 图标（Word 批注中不显示颜色图标，保持纯文本）"""
    return _EMOJI_RE.sub('', text)


def local_name(tag):
    return tag.split('}')[-1] if '}' in tag else tag

def copy_run_properties(source_run_elem):
    """复制原 run 的完整 rPr（字体、字号、颜色等），无 rPr 时返回 None"""
    rpr = source_run_elem.find(W_RPR)
    if rpr is not None:
        new_rpr = etree.Element(W_RPR)
        for child in rpr:
            new_rpr.append(copy.deepcopy(child))
        return new_rpr
    return None

def _build_run_content(r, text, rpr_elem, text_tag='t'):
    """在 w:r 内部按 \\n / \\t 构建 w:t / w:br / w:tab 交错序列"""
    if rpr_elem is not None:
        r.append(copy.deepcopy(rpr_elem))
    parts = text.split('\n')
    for i, part in enumerate(parts):
        if i > 0:
            etree.SubElement(r, W_BR)
        if part:
            tab_parts = part.split('\t')
            for j, tab_part in enumerate(tab_parts):
                if j > 0:
                    etree.SubElement(r, W_TAB)
                if tab_part:
                    elem = etree.SubElement(r, f'{{{W}}}{text_tag}')
                    elem.text = tab_part
                    elem.set(XML_SPACE, 'preserve')
    return r

def _add_tracked_style(rpr_elem, style_name):
    """为修订 run 追加 Del/Ins 样式。原 run 无 rPr 时返回 None（绝不凭空创建 rPr）。"""
    if rpr_elem is None:
        return None  # Word 依据 w:del/w:ins 元素自动渲染删除线/下划线
    rpr = copy.deepcopy(rpr_elem)
    rs = etree.SubElement(rpr, W_RSTYLE)
    rs.set(W_ID, style_name)
    return rpr

def make_del_run(text, rpr_elem=None, author=DEFAULT_AUTHOR):
    """创建 w:del（修订删除）"""
    del_elem = etree.Element(W_DEL)
    del_elem.set(W_ID, str(next_id()))
    del_elem.set(f'{{{W}}}author', author)
    del_elem.set(f'{{{W}}}date', now_str())
    r = etree.Element(W_R)
    new_rpr = _add_tracked_style(rpr_elem, 'Del')
    _build_run_content(r, text, new_rpr, 'delText')
    del_elem.append(r)
    return del_elem

def make_ins_run(text, rpr_elem=None, author=DEFAULT_AUTHOR):
    """创建 w:ins（修订插入）"""
    ins_elem = etree.Element(W_INS)
    ins_elem.set(W_ID, str(next_id()))
    ins_elem.set(f'{{{W}}}author', author)
    ins_elem.set(f'{{{W}}}date', now_str())
    r = etree.Element(W_R)
    new_rpr = _add_tracked_style(rpr_elem, 'Ins')
    _build_run_content(r, text, new_rpr, 't')
    ins_elem.append(r)
    return ins_elem

def make_run(text, rpr_elem=None):
    """创建普通 w:r"""
    r = etree.Element(W_R)
    return _build_run_content(r, text, rpr_elem, 't')

def get_run_text(run_elem):
    """完整还原 run 的文本：w:t 取文本，w:br→\\n，w:tab→\\t"""
    texts = []
    for child in run_elem:
        if child.tag == W_T:
            if child.text:
                texts.append(child.text)
        elif child.tag == W_BR:
            texts.append('\n')
        elif child.tag == W_TAB:
            texts.append('\t')
    return ''.join(texts)

def get_ins_text(ins_elem):
    """还原 w:ins 内全部文本（w:r/w:t）"""
    texts = []
    for r in ins_elem.findall(W_R):
        texts.append(get_run_text(r))
    return ''.join(texts)

def get_del_text(del_elem):
    """还原 w:del 内全部文本（w:r/w:delText）"""
    texts = []
    for r in del_elem.findall(W_R):
        for child in r:
            if child.tag == W_DELTEXT and child.text:
                texts.append(child.text)
    return ''.join(texts)

def get_rpr_of_container(elem):
    """获取 w:r 或 w:ins/w:del 内 w:r 的 rPr（不含修订样式）"""
    if elem.tag == W_R:
        return copy_run_properties(elem)
    r = elem.find(W_R)
    if r is not None:
        rpr = copy_run_properties(r)
        if rpr is not None:
            for rs in rpr.findall(W_RSTYLE):
                if rs.get(W_ID) in ('Del', 'Ins'):
                    rpr.remove(rs)
        return rpr
    return None


# ============================================================
# 文本容器收集（跨 run 匹配的核心）
# ============================================================

def collect_containers(p_elem):
    """
    收集段落中参与文本匹配的容器：普通 w:r 与 w:ins（视为"修订后已接受"的文本）。
    返回 (containers, full_text)，containers 为 [(elem, text, is_ins), ...]。
    w:del 不算（已删除文本不可作为匹配源）；空 run（如 commentReference run）计入
    但文本为空，不影响匹配。
    """
    containers = []
    parts = []
    for child in p_elem:
        if child.tag == W_R:
            t = get_run_text(child)
            containers.append((child, t, False))
            parts.append(t)
        elif child.tag == W_INS:
            t = get_ins_text(child)
            containers.append((child, t, True))
            parts.append(t)
    return containers, ''.join(parts)


# ============================================================
# replace 最小化拆分计划（公共部分保留，差异先 DEL 后 INS）
# ============================================================

def _lcs_substring(old, new):
    """返回 (长度, old 结束下标, new 结束下标) 的最长公共子串（取最左出现）。
    滚动数组实现：仅保留两行 DP，内存 O(n)、时间 O(m×n)。"""
    m, n = len(old), len(new)
    best = 0
    best_i = -1
    best_j = -1
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        row = [0] * (n + 1)
        oi = old[i - 1]
        for j in range(1, n + 1):
            if oi == new[j - 1]:
                v = prev[j - 1] + 1
                row[j] = v
                if v > best:
                    best = v
                    best_i = i
                    best_j = j
        prev = row
    return best, best_i, best_j


def _plan_rec(old, new, plan, min_common):
    """递归生成修订计划：公共块 keep，差异块先 del 后 ins。"""
    if not old and not new:
        return
    if not old:
        plan.append(('ins', new))
        return
    if not new:
        plan.append(('del', old))
        return
    if len(old) * len(new) > LCS_LIMIT:
        # 超长降级：公共前后缀拆分
        prefix = 0
        while prefix < len(old) and prefix < len(new) and old[prefix] == new[prefix]:
            prefix += 1
        suffix = 0
        while (suffix < len(old) - prefix and suffix < len(new) - prefix
               and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]):
            suffix += 1
        if prefix:
            plan.append(('keep', old[:prefix]))
        mid_old = old[prefix:len(old) - suffix]
        mid_new = new[prefix:len(new) - suffix]
        if mid_old:
            plan.append(('del', mid_old))
        if mid_new:
            plan.append(('ins', mid_new))
        if suffix:
            plan.append(('keep', old[len(old) - suffix:]))
        return
    best, bi, bj = _lcs_substring(old, new)
    if best < min_common:
        plan.append(('del', old))
        plan.append(('ins', new))
        return
    common = old[bi - best:bi]
    _plan_rec(old[:bi - best], new[:bj - best], plan, min_common)
    plan.append(('keep', common))
    _plan_rec(old[bi:], new[bj:], plan, min_common)


def plan_replace(old_text, new_text, min_common=MIN_COMMON_LEN):
    """生成替换计划 [(kind, text)]：keep 保留 / del 删除 / ins 插入。"""
    plan = []
    _plan_rec(old_text, new_text, plan, min_common)
    return plan


# ============================================================
# 段落级修订操作（跨 run，返回锚定元素 + 修订 id 列表）
# ============================================================

def replace_text_in_para(para, old_text, new_text, author=DEFAULT_AUTHOR):
    """
    在段落中用修订标记替换文字：跨 run 匹配 old_text，按最小化计划生成
    DEL/INS（公共部分保留，差异先 DEL 后 INS）。
    返回 (ok, start_elem, end_elem, del_ids, ins_ids)。
    """
    p_elem = para._p
    containers, full_text = collect_containers(p_elem)
    if not full_text or old_text not in full_text:
        return False, None, None, [], []

    start = full_text.index(old_text)
    end = start + len(old_text)
    plan = plan_replace(old_text, new_text)

    # 第一步：遍历容器，切出 before / match / after；非容器元素 deepcopy 保留
    # 顺序铁律：区间前容器立即保留；跨区间容器切出 before（立即）+
    # match（segments，第二步生成修订）+ after（延迟）；区间后容器延迟。
    new_children = []
    pending = []   # after 片段 + 区间后容器，必须在 match 修订之后输出
    segments = []   # (is_ins, rpr, match_text)，按文档顺序，仅区间内片段
    pos = 0
    for child in p_elem:
        if child.tag == W_R:
            text = get_run_text(child)
            is_ins = False
        elif child.tag == W_INS:
            text = get_ins_text(child)
            is_ins = True
        else:
            new_children.append(copy.deepcopy(child))
            continue
        run_end = pos + len(text)
        if run_end <= start:
            new_children.append(copy.deepcopy(child))
        elif pos >= end:
            pending.append(copy.deepcopy(child))
        else:
            rpr = get_rpr_of_container(child)
            ls = max(0, start - pos)
            le = min(len(text), end - pos)
            before, match, after = text[:ls], text[ls:le], text[le:]
            if before:
                new_children.append(make_ins_run(before, rpr, author) if is_ins
                                    else make_run(before, rpr))
            if match:
                segments.append((is_ins, rpr, match))
            if after:
                pending.append(make_ins_run(after, rpr, author) if is_ins
                               else make_run(after, rpr))
        pos = run_end

    # 第二步：计划与片段双指针消费（公共保留、差异先 DEL 后 INS，跨片段正确推进）
    seg_idx = 0
    seg_pos = 0
    last_rpr = None
    del_elems = []
    ins_elems = []

    def _consume(ptxt, kind):
        """从片段队列消费 len(ptxt) 文本（keep/del 块可能跨多个片段）。"""
        nonlocal seg_idx, seg_pos, last_rpr
        remaining = ptxt
        while remaining and seg_idx < len(segments):
            is_ins, rpr, seg_text = segments[seg_idx]
            avail = seg_text[seg_pos:]
            take = avail[:len(remaining)]
            if take:
                last_rpr = rpr
                if kind == 'del':
                    d = make_del_run(take, rpr, author)
                    new_children.append(d)
                    del_elems.append(d)
                else:  # keep：公共部分保留为普通 run（不删不加）
                    new_children.append(make_run(take, rpr))
                remaining = remaining[len(take):]
                seg_pos += len(take)
            if seg_pos >= len(seg_text):
                seg_idx += 1
                seg_pos = 0
        return not remaining

    for kind, ptxt in plan:
        if kind == 'ins':
            rpr = last_rpr if last_rpr is not None else (
                segments[seg_idx][1] if seg_idx < len(segments) else None)
            i = make_ins_run(ptxt, rpr, author)
            new_children.append(i)
            ins_elems.append(i)
        else:
            _consume(ptxt, kind)

    # match 修订块之后，再输出 after 片段与区间后容器（保持原文档顺序）
    for child in pending:
        new_children.append(child)

    if not del_elems and not ins_elems:
        return False, None, None, [], []

    for child in list(p_elem):
        p_elem.remove(child)
    for child in new_children:
        p_elem.append(child)

    start_elem = del_elems[0] if del_elems else ins_elems[0]
    end_elem = ins_elems[-1] if ins_elems else del_elems[-1]
    del_ids = [d.get(W_ID) for d in del_elems]
    ins_ids = [i.get(W_ID) for i in ins_elems]
    return True, start_elem, end_elem, del_ids, ins_ids


def insert_after_text(para, anchor_text, insert_text, author=DEFAULT_AUTHOR):
    """
    在段落中指定文本之后插入新文本（修订标记 INS），锚点落在 run 内部时
    精确切分该 run、在锚点正后方插入。
    返回 (ok, ins_elem, ins_elem, [], [ins_id])。
    """
    p_elem = para._p
    containers, full_text = collect_containers(p_elem)
    if not full_text or anchor_text not in full_text:
        return False, None, None, [], []

    anchor_end = full_text.index(anchor_text) + len(anchor_text)

    new_children = []
    ins_elem = None
    inserted = False
    pos = 0

    for child in p_elem:
        if child.tag == W_R:
            text = get_run_text(child)
        elif child.tag == W_INS:
            text = get_ins_text(child)
        else:
            new_children.append(copy.deepcopy(child))
            continue
        run_end = pos + len(text)
        new_children.append(copy.deepcopy(child))
        if not inserted and text and pos <= anchor_end <= run_end:
            rpr = get_rpr_of_container(child)
            ins_elem = make_ins_run(insert_text, rpr, author)
            new_children.append(ins_elem)
            inserted = True
        pos = run_end

    if not inserted:
        return False, None, None, [], []

    for child in list(p_elem):
        p_elem.remove(child)
    for child in new_children:
        p_elem.append(child)

    return True, ins_elem, ins_elem, [], [ins_elem.get(W_ID)]


def delete_text_in_para(para, text_to_delete, author=DEFAULT_AUTHOR):
    """用修订标记删除指定文字（无对应插入内容）。返回 (ok, del_start, del_end, del_ids, [])。"""
    ok, s, e, del_ids, _ = replace_text_in_para(para, text_to_delete, "", author)
    return ok, s, e, del_ids, []


# ============================================================
# 表格单元格级修订操作
# ============================================================

def replace_text_in_cell(cell, old_text, new_text, author=DEFAULT_AUTHOR):
    """在单元格内逐段落查找并修订替换。"""
    for para in cell.paragraphs:
        if para.text and old_text in para.text:
            ok, s, e, dids, iids = replace_text_in_para(para, old_text, new_text, author)
            if ok:
                return True, para, s, e, dids, iids
    return False, None, None, None, [], []


def insert_after_in_cell(cell, anchor_text, insert_text, author=DEFAULT_AUTHOR):
    """在单元格内指定文本之后插入新文本。"""
    for para in cell.paragraphs:
        if para.text and anchor_text in para.text:
            ok, s, e, dids, iids = insert_after_text(para, anchor_text, insert_text, author)
            if ok:
                return True, para, s, e, dids, iids
    return False, None, None, None, [], []


def delete_text_in_cell(cell, text_to_delete, author=DEFAULT_AUTHOR):
    """在单元格内用修订标记删除指定文字。"""
    for para in cell.paragraphs:
        if para.text and text_to_delete in para.text:
            ok, s, e, dids, iids = replace_text_in_para(para, text_to_delete, "", author)
            if ok:
                return True, para, s, e, dids, iids
    return False, None, None, None, [], []


# ============================================================
# 格式修订（action=format：w:rPrChange / w:pPrChange，只改格式不动文字）
# ============================================================

def _apply_run_format(r_elem, new_format, author=DEFAULT_AUTHOR):
    """对单个 w:r 应用字符格式修订，追加 w:rPrChange（内嵌旧 rPr 快照）。"""
    rpr = r_elem.find(f'{{{W}}}rPr')
    old_rpr = copy.deepcopy(rpr) if rpr is not None else None
    if rpr is None:
        rpr = etree.Element(f'{{{W}}}rPr')
        r_elem.insert(0, rpr)
    for rc in rpr.findall(f'{{{W}}}rPrChange'):
        rpr.remove(rc)

    # 布尔开关：true=裸元素，false=删除元素
    for key, tag in (('bold', 'b'), ('bold', 'bCs'), ('italic', 'i'), ('italic', 'iCs')):
        pass
    for key in ('b', 'bCs'):
        el = rpr.find(f'{{{W}}}{key}')
        if new_format.get('bold') is True:
            if el is None:
                etree.SubElement(rpr, f'{{{W}}}{key}')
        elif new_format.get('bold') is False and el is not None:
            rpr.remove(el)
    for key in ('i', 'iCs'):
        el = rpr.find(f'{{{W}}}{key}')
        if new_format.get('italic') is True:
            if el is None:
                etree.SubElement(rpr, f'{{{W}}}{key}')
        elif new_format.get('italic') is False and el is not None:
            rpr.remove(el)
    if 'underline' in new_format:
        u = rpr.find(f'{{{W}}}u')
        if new_format['underline']:
            if u is None:
                u = etree.SubElement(rpr, f'{{{W}}}u')
            u.set(f'{{{W}}}val', 'single')
        elif u is not None:
            rpr.remove(u)
    if 'font' in new_format:
        rf = rpr.find(f'{{{W}}}rFonts')
        if rf is None:
            rf = etree.SubElement(rpr, f'{{{W}}}rFonts')
        for attr in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
            rf.set(f'{{{W}}}{attr}', new_format['font'])
    if 'font_size_pt' in new_format:
        sz_val = str(int(float(new_format['font_size_pt']) * 2))
        for key in ('sz', 'szCs'):
            el = rpr.find(f'{{{W}}}{key}')
            if el is None:
                el = etree.SubElement(rpr, f'{{{W}}}{key}')
            el.set(f'{{{W}}}val', sz_val)
    if 'color' in new_format:
        c = rpr.find(f'{{{W}}}color')
        if c is None:
            c = etree.SubElement(rpr, f'{{{W}}}color')
        c.set(f'{{{W}}}val', str(new_format['color']).lstrip('#'))

    # rPrChange 必须是 rPr 的最后一个子元素，内嵌旧 rPr 快照
    ch = etree.SubElement(rpr, f'{{{W}}}rPrChange')
    ch.set(f'{{{W}}}id', str(next_id()))
    ch.set(f'{{{W}}}author', author)
    ch.set(f'{{{W}}}date', now_str())
    if old_rpr is not None:
        ch.append(old_rpr)
    return True


def _apply_para_format(p_elem, new_format, author=DEFAULT_AUTHOR):
    """对段落 pPr 应用段落格式修订，追加 w:pPrChange（内嵌旧 pPr 快照）。"""
    ppr = p_elem.find(f'{{{W}}}pPr')
    old_ppr = copy.deepcopy(ppr) if ppr is not None else None
    if ppr is None:
        ppr = etree.Element(f'{{{W}}}pPr')
        p_elem.insert(0, ppr)
    for rc in ppr.findall(f'{{{W}}}pPrChange'):
        ppr.remove(rc)

    if 'align' in new_format:
        jc = ppr.find(f'{{{W}}}jc')
        if jc is None:
            jc = etree.SubElement(ppr, f'{{{W}}}jc')
        jc.set(f'{{{W}}}val', new_format['align'])
    if 'line_spacing' in new_format:
        sp = ppr.find(f'{{{W}}}spacing')
        if sp is None:
            sp = etree.SubElement(ppr, f'{{{W}}}spacing')
        sp.set(f'{{{W}}}line', str(int(float(new_format['line_spacing']) * 240)))
        sp.set(f'{{{W}}}lineRule', 'auto')
    if 'first_line_indent_pt' in new_format:
        ind = ppr.find(f'{{{W}}}ind')
        if ind is None:
            ind = etree.SubElement(ppr, f'{{{W}}}ind')
        ind.set(f'{{{W}}}firstLine', str(int(float(new_format['first_line_indent_pt']) * 20)))

    ch = etree.SubElement(ppr, f'{{{W}}}pPrChange')
    ch.set(f'{{{W}}}id', str(next_id()))
    ch.set(f'{{{W}}}author', author)
    ch.set(f'{{{W}}}date', now_str())
    if old_ppr is not None:
        ch.append(old_ppr)
    return True


def apply_format_to_para(para, item, author=DEFAULT_AUTHOR):
    """
    对段落执行格式修订（action=format）。
    level=run：仅改 run_text 所在 run（省略 run_text 则改段落全部 run）。
    level=para：改段落标记（pPr）。
    返回 (ok, anchor_elem_or_None, desc)。
    """
    new_format = item.get('new_format', {}) or {}
    if not new_format:
        return False, None, 'new_format 为空'
    level = item.get('level', 'run')
    p_elem = para._p

    if level == 'para':
        _apply_para_format(p_elem, new_format, author)
        return True, None, '段落格式'

    # level=run
    run_text = item.get('run_text')
    targets = []
    for child in p_elem:
        if local_name(child.tag) != 'r':
            continue
        t = get_run_text(child)
        if run_text is None:
            targets.append(child)
        elif run_text in t:
            targets.append(child)
    if not targets:
        return False, None, f'未找到 run_text "{run_text}"'
    for r in targets:
        _apply_run_format(r, new_format, author)
    return True, targets[0], '字符格式'


# ============================================================
# 批注操作（CM 基础设施 + 按 w:id 精确锚定）
# ============================================================

def resolve_anchor_by_ids(p_elem, del_ids, ins_ids):
    """
    按 w:id 在最终段落结构中查找本次修订生成的 DEL/INS 元素。
    w:id 是 XML 属性，段落重建（deepcopy）后依然保留，唯一且稳定。
    返回 (start_elem, end_elem)：**按文档顺序**的第一个 → 最后一个修订元素。
    （坑 ③：LCS 公共子串可出现在 old 开头/new 末尾，拆分会产生 ins→keep→del
     顺序，DEL 不一定在 INS 前；固定"第一个 DEL → 最后一个 INS"会导致
     Start/End 颠倒，必须按文档顺序取首尾。）
    """
    id_set = set(del_ids) | set(ins_ids)
    if not id_set:
        return None, None
    revs = [c for c in p_elem
            if c.tag in (W_DEL, W_INS) and c.get(W_ID) in id_set]
    if not revs:
        return None, None
    return revs[0], revs[-1]


def _move_comment_markers(p_elem, comment_id, start_elem, end_elem):
    """
    将 comment_id 的 commentRangeStart / commentRangeEnd / commentReference run
    从 CM 默认位置移动到 start_elem 之前 ~ end_elem 之后。
    位置铁律：同段落、同级（直接子元素层），Start 在第一个修订元素之前、
    End 在最后一个修订元素之后；禁止跨段、禁止嵌套进 ins/del 内部。
    """
    cid_str = str(comment_id)
    children = list(p_elem)
    crs = cre = cref_run = None
    for child in children:
        if child.tag == W_CRS and child.get(W_ID) == cid_str:
            crs = child
        elif child.tag == W_CRE and child.get(W_ID) == cid_str:
            cre = child
        elif child.tag == W_R:
            for sub in child:
                if sub.tag == W_CREF and sub.get(W_ID) == cid_str:
                    cref_run = child
                    break

    if crs is None or cre is None or cref_run is None:
        raise RuntimeError(f'批注 {comment_id} 的标记不完整（crs={crs is not None}, '
                           f'cre={cre is not None}, cref={cref_run is not None}）')

    # 断言：start/end 必须是段落直接子元素（同级、不嵌套）
    if start_elem not in children or end_elem not in children:
        raise RuntimeError(f'批注 {comment_id} 锚定元素不是段落直接子元素，拒绝移动')
    if children.index(start_elem) > children.index(end_elem):
        raise RuntimeError(f'批注 {comment_id} 锚定元素顺序错误（start 在 end 之后）')

    p_elem.remove(crs)
    p_elem.remove(cre)
    p_elem.remove(cref_run)

    idx = list(p_elem).index(start_elem)
    p_elem.insert(idx, crs)
    idx = list(p_elem).index(end_elem)
    p_elem.insert(idx + 1, cre)
    idx = list(p_elem).index(cre)
    p_elem.insert(idx + 1, cref_run)


def add_comment_anchored(doc, mgr, para, text, author=DEFAULT_AUTHOR,
                         start_elem=None, end_elem=None):
    """
    添加批注并精确锚定到 start_elem ~ end_elem（修订元素）。
    实现：先用 CM 创建批注（保证 WPS 所需全部基础设施），再手动移动标记。
    段落没有任何 w:r 时（如整段被删除），临时插入空 run 供 CM 锚定，随后移除。
    返回 comment id。
    """
    text = strip_emojis(text)
    p_elem = para._p

    runs = [c for c in p_elem if c.tag == W_R]
    temp_run = None
    if not runs:
        temp_run = etree.Element(W_R)
        p_elem.insert(0, temp_run)
        runs = [temp_run]

    cid = mgr.add_comment(paragraph=para, text=text,
                          author=PersonInfo(author=author),
                          start_run=0, end_run=0)

    if start_elem is not None and end_elem is not None:
        _move_comment_markers(p_elem, cid, start_elem, end_elem)

    if temp_run is not None and temp_run.getparent() is not None:
        p_elem.remove(temp_run)

    _split_comment_newlines(mgr, cid)
    return cid


def add_comment_anchored_multi(doc, mgr, anchors, text, author=DEFAULT_AUTHOR):
    """
    为同一条款的多处修订添加【一条】批注，范围覆盖全部修订锚点（可跨段落）。
    anchors: [(para, start_elem, end_elem), ...] 按文档顺序。
    commentRangeStart 放第一段第一个 start_elem 之前，commentRangeEnd 与
    commentReference 放最后一段最后一个 end_elem 之后（Word 原生跨段批注，
    中间段落自然被范围覆盖）。
    """
    text = strip_emojis(text)
    first_para, first_s, _ = anchors[0]
    last_para, _, last_e = anchors[-1]
    p_first = first_para._p
    p_last = last_para._p

    # CM 创建批注（挂第一段，保证 WPS 所需全部基础设施）
    runs = [c for c in p_first if c.tag == W_R]
    temp_run = None
    if not runs:
        temp_run = etree.Element(W_R)
        p_first.insert(0, temp_run)
        runs = [temp_run]
    cid = mgr.add_comment(paragraph=first_para, text=text,
                          author=PersonInfo(author=author),
                          start_run=0, end_run=0)
    if temp_run is not None and temp_run.getparent() is not None:
        p_first.remove(temp_run)

    # 从第一段移除 crs / cre / cref（CM 默认都挂在第一段）
    cid_str = str(cid)
    crs = cre = cref_run = None
    for child in list(p_first):
        if child.tag == W_CRS and child.get(W_ID) == cid_str:
            crs = child
            p_first.remove(child)
        elif child.tag == W_CRE and child.get(W_ID) == cid_str:
            cre = child
            p_first.remove(child)
        elif child.tag == W_R:
            for sub in child:
                if sub.tag == W_CREF and sub.get(W_ID) == cid_str:
                    cref_run = child
                    p_first.remove(child)
                    break
    if crs is None or cre is None or cref_run is None:
        raise RuntimeError(f'批注 {cid} 的标记不完整（crs={crs is not None}, '
                           f'cre={cre is not None}, cref={cref_run is not None}）')

    # crs 插到第一段第一个修订元素之前
    children = list(p_first)
    if first_s not in children:
        raise RuntimeError(f'批注 {cid} 首锚点不是段落直接子元素，拒绝移动')
    p_first.insert(children.index(first_s), crs)

    # cre + cref 插到最后一段最后一个修订元素之后
    children = list(p_last)
    if last_e not in children:
        raise RuntimeError(f'批注 {cid} 尾锚点不是段落直接子元素，拒绝移动')
    p_last.insert(children.index(last_e) + 1, cre)
    p_last.insert(children.index(last_e) + 2, cref_run)
    _split_comment_newlines(mgr, cid)
    return cid


def add_comment_to_para(doc, mgr, para, text, author=DEFAULT_AUTHOR):
    """为段落添加 Word 批注（comment_only 场景，锚定整个段落文本）。"""
    text = strip_emojis(text)
    p_elem = para._p
    runs = [c for c in p_elem if c.tag == W_R]
    temp_run = None
    if not runs:
        temp_run = etree.Element(W_R)
        p_elem.insert(0, temp_run)
        runs = [temp_run]
    cid = mgr.add_comment(paragraph=para, text=text,
                          author=PersonInfo(author=author),
                          start_run=0, end_run=len(runs) - 1)
    if temp_run is not None and temp_run.getparent() is not None:
        p_elem.remove(temp_run)
    _split_comment_newlines(mgr, cid)
    return cid


def add_comment_to_cell(doc, mgr, cell, text, author=DEFAULT_AUTHOR):
    """为表格单元格添加批注：优先锚定第一个非空段落；全空时锚定第一个段落。"""
    target_para = None
    for p in cell.paragraphs:
        if p.text.strip():
            target_para = p
            break
    if target_para is None and cell.paragraphs:
        target_para = cell.paragraphs[0]
    if target_para is not None:
        return add_comment_to_para(doc, mgr, target_para, text, author)
    return False


def resolve_target(doc, item, paras=None):
    """按 scope 解析目标段落对象。返回 (para, 描述字符串) 或 (None, 错误信息)。
    paras: 可选的已缓存段落列表（避免每次调用 doc.paragraphs 全文档扫描）。"""
    scope = item.get("scope", "para")
    if scope == "cell":
        ti = item.get("table", -1)
        ri = item.get("row", -1)
        ci = item.get("cell", -1)
        desc = f"表{ti + 1}.R{ri + 1}.C{ci + 1}"
        try:
            cell = doc.tables[ti].rows[ri].cells[ci]
            return cell, desc
        except IndexError:
            return None, f"单元格越界: {desc}"
    else:
        idx = item.get("para_index", -1)
        desc = f"段落{idx}"
        if paras is None:
            paras = doc.paragraphs
        if 0 <= idx < len(paras):
            return paras[idx], desc
        return None, f"段落索引越界: {idx}"


def clause_label(item, idx):
    """条款定位标签：优先 item.clause / item.条款号，否则条目序号 idx+1。"""
    return str(item.get("clause") or item.get("条款号") or (idx + 1))


def tracked_note(comment, kind, label):
    """修订类批注自动追加「本条对应第X条的…」；已含「本条对应」时不重复追加。
    label 形如「第六条」时直接使用，形如序号「1」时补成「第1条」。"""
    if not comment or '本条对应' in comment:
        return comment
    note = {'both': '删除+新增', 'del': '删除', 'ins': '新增', 'format': '格式修订'}.get(kind, '修订')
    label = str(label)
    loc = label if (label.startswith('第') and label.endswith('条')) else f'第{label}条'
    return f"{comment}\n本条对应{loc}的{note}"


def apply_items(doc, mgr, items, author=DEFAULT_AUTHOR, merge_by_clause=False):
    """
    严格两阶段执行：
      阶段 1 修订：逐条执行替换/删除/插入/格式修订，记录 (para, del_ids, ins_ids)。
      阶段 2 批注：修订全部完成后，按 w:id 定位锚点，为带 comment 的条目添加批注。
        默认逐条批注（一个清单条目 = 一条批注，不合并）；
        merge_by_clause=True 时按 clause 合并（一条款一条批注，可跨段）。
    返回: (results, stats)
    """
    results = []
    stats = {"revised": 0, "commented": 0, "failed": 0}
    anchors = {}   # idx -> (para, del_ids, ins_ids, desc, kind, label)
    comment_only_items = []
    paras = doc.paragraphs   # 缓存一次，避免 resolve_target 反复全文档扫描

    # ─────────── 阶段 1: 修订 ───────────
    for idx, item in enumerate(items):
        action = item.get("action", "replace")
        comment_only = item.get("comment_only", False)
        tag = f"[{idx + 1}]"
        label = clause_label(item, idx)

        target, desc = resolve_target(doc, item, paras)
        if target is None:
            results.append(f"{tag} ❌ {desc}")
            stats["failed"] += 1
            continue

        if comment_only:
            comment_only_items.append((idx, item, target, desc))
            continue

        revised = False
        para = None
        del_ids, ins_ids = [], []
        kind = 'both'

        if action == 'format':
            scope = item.get("scope", "para")
            if scope == "cell":
                para = None
                for p in target.paragraphs:
                    if p.text.strip():
                        para = p
                        break
                if para is None and target.paragraphs:
                    para = target.paragraphs[0]
                if para is None:
                    results.append(f"{tag} ❌ {desc}：单元格无段落，格式修订失败")
                    stats["failed"] += 1
                    continue
            else:
                para = target
            revised, anchor_elem, fdesc = apply_format_to_para(para, item, author)
            if revised:
                stats["revised"] += 1
                kind = 'format'
                anchors[idx] = (para, del_ids, ins_ids, desc, kind, label, anchor_elem)
                results.append(f"{tag} ✅ {desc}：{fdesc}修订 {item.get('new_format', {})}")
            else:
                results.append(f"{tag} ⚠️ {desc}：格式修订失败（{fdesc}）")
                stats["failed"] += 1
            continue

        if item.get("scope", "para") == "cell":
            if action == "replace":
                revised, para, s_elem, e_elem, del_ids, ins_ids = replace_text_in_cell(
                    target, item.get("old", ""), item.get("new", ""), author)
            elif action == "delete":
                revised, para, s_elem, e_elem, del_ids, ins_ids = delete_text_in_cell(
                    target, item.get("old", ""), author)
            elif action == "insert":
                revised, para, s_elem, e_elem, del_ids, ins_ids = insert_after_in_cell(
                    target, item.get("anchor", ""), item.get("new", ""), author)
            else:
                results.append(f"{tag} ⚠️ 未知 action: {action}")
                stats["failed"] += 1
                continue
        else:
            if action == "replace":
                revised, s_elem, e_elem, del_ids, ins_ids = replace_text_in_para(
                    target, item.get("old", ""), item.get("new", ""), author)
                para = target
            elif action == "delete":
                revised, s_elem, e_elem, del_ids, ins_ids = delete_text_in_para(
                    target, item.get("old", ""), author)
                para = target
            elif action == "insert":
                revised, s_elem, e_elem, del_ids, ins_ids = insert_after_text(
                    target, item.get("anchor", ""), item.get("new", ""), author)
                para = target
            else:
                results.append(f"{tag} ⚠️ 未知 action: {action}")
                stats["failed"] += 1
                continue

        if not revised:
            old_preview = item.get("old", item.get("anchor", ""))[:30]
            results.append(f"{tag} ⚠️ {desc}：未找到目标文本 '{old_preview}'，已跳过")
            stats["failed"] += 1
            continue

        stats["revised"] += 1
        kind = 'del' if action == 'delete' else ('ins' if action == 'insert' else 'both')
        anchors[idx] = (para, del_ids, ins_ids, desc, kind, label, None)
        if action == "replace":
            results.append(f"{tag} ✅ {desc}：'{item.get('old', '')}' → '{item.get('new', '')}'")
        elif action == "delete":
            results.append(f"{tag} ✅ {desc}：删除 '{item.get('old', '')}'")
        elif action == "insert":
            results.append(f"{tag} ✅ {desc}：在 '{item.get('anchor', '')}' 后插入 '{item.get('new', '')}'")

    # ─────────── 阶段 2: 批注（先修订后批注） ───────────
    # 默认：一个清单条目（item）= 一条批注，逐条锚定各自修订处，不合并
    # （2026-09-01 用户明确：修订清单逐条给，批注必须逐条，禁止把同一条款子项合并）
    # 可选：items 顶层 "merge_by_clause": true 时恢复按条款合并（一条款一条批注，可跨段）
    body = doc.element.body
    para_pos = {}
    for _i, _p in enumerate(body.iter(f'{{{W}}}p')):
        para_pos[id(_p)] = _i

    merge_by_clause = bool(merge_by_clause)

    if merge_by_clause:
        groups = {}    # clause -> [(idx, item, anchor_tuple)]
        order = []     # clause 首次出现顺序（即文档顺序）
        for idx, item in enumerate(items):
            comment_only = item.get("comment_only", False)
            tag = f"[{idx + 1}]"
            if comment_only:
                comment = item.get("comment", "")
                if not comment:
                    continue
                if comment_only_items:
                    _, _, target, desc = comment_only_items.pop(0)
                else:
                    target, desc = resolve_target(doc, item, paras)
                if target is None:
                    results.append(f"{tag} ⚠️ {desc}：批注添加失败（目标不存在）")
                    stats["failed"] += 1
                    continue
                if item.get("scope", "para") == "cell":
                    add_comment_to_cell(doc, mgr, target, comment, author)
                else:
                    add_comment_to_para(doc, mgr, target, comment, author)
                stats["commented"] += 1
                results.append(f"{tag} 💬 批注 {desc}")
                continue

            if idx not in anchors:
                continue  # 修订失败，无锚点，跳过批注（已在阶段1记录失败）
            clause = item.get("clause", "") or f"第{idx + 1}项"
            if clause not in groups:
                groups[clause] = []
                order.append(clause)
            groups[clause].append((idx, item, anchors[idx]))

        for clause in order:
            entries = groups[clause]
            # 批注文本：组内第一个带 comment 的项（一条款一条批注，文本由清单提供）
            comment = next((it.get("comment", "") for _, it, _ in entries if it.get("comment")), "")
            if not comment:
                continue
            anchor_list = []
            ok = True
            for idx, item, (para, del_ids, ins_ids, desc, kind, label, fmt_anchor) in entries:
                if kind == 'format':
                    anchor_list.append((para, fmt_anchor, fmt_anchor))
                    continue
                s_elem, e_elem = resolve_anchor_by_ids(para._p, del_ids, ins_ids)
                if s_elem is None or e_elem is None:
                    results.append(f"[{idx + 1}] ⚠️ {desc}：修订后无法按 id 定位批注锚点，批注已跳过")
                    stats["failed"] += 1
                    ok = False
                    break
                anchor_list.append((para, s_elem, e_elem))
            if not ok or not anchor_list:
                continue
            # 锚点按文档顺序排序（同条款跨段合并时保证 Start 在 End 之前）
            anchor_list.sort(key=lambda a: para_pos.get(id(a[0]._p), 0))
            # 一处条款 = 一条批注：范围覆盖该条款全部修订锚点（同段或跨段）
            add_comment_anchored_multi(doc, mgr, anchor_list, comment, author)
            stats["commented"] += 1
            if len(entries) == 1:
                results.append(f"💬 批注 {clause}（精确锚定修订处）")
            else:
                results.append(f"💬 批注 {clause}（{len(entries)} 处修订合并为一条批注）")
    else:
        # 默认：逐条批注 —— 每个 item 一条独立批注，锚定该 item 自己的修订处
        for idx, item in enumerate(items):
            tag = f"[{idx + 1}]"
            comment_only = item.get("comment_only", False)
            if comment_only:
                comment = item.get("comment", "")
                if not comment:
                    continue
                if comment_only_items:
                    _, _, target, desc = comment_only_items.pop(0)
                else:
                    target, desc = resolve_target(doc, item, paras)
                if target is None:
                    results.append(f"{tag} ⚠️ {desc}：批注添加失败（目标不存在）")
                    stats["failed"] += 1
                    continue
                if item.get("scope", "para") == "cell":
                    add_comment_to_cell(doc, mgr, target, comment, author)
                else:
                    add_comment_to_para(doc, mgr, target, comment, author)
                stats["commented"] += 1
                results.append(f"{tag} 💬 批注 {desc}")
                continue

            if idx not in anchors:
                continue  # 修订失败，无锚点，跳过批注（已在阶段1记录失败）
            comment = item.get("comment", "")
            if not comment:
                continue
            para, del_ids, ins_ids, desc, kind, label, fmt_anchor = anchors[idx]
            if kind == 'format':
                add_comment_anchored(doc, mgr, para, comment, author, fmt_anchor, fmt_anchor)
            else:
                s_elem, e_elem = resolve_anchor_by_ids(para._p, del_ids, ins_ids)
                if s_elem is None or e_elem is None:
                    results.append(f"{tag} ⚠️ {desc}：修订后无法按 id 定位批注锚点，批注已跳过")
                    stats["failed"] += 1
                    continue
                add_comment_anchored(doc, mgr, para, comment, author, s_elem, e_elem)
            stats["commented"] += 1
            results.append(f"{tag} 💬 批注 {desc}")

    return results, stats


def main():
    if len(sys.argv) < 4 or "--items" not in sys.argv:
        print("用法: python3 revision_edit.py <input.docx> <output.docx> --items items.json")
        print("items.json 格式见脚本头部文档")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    items_path = sys.argv[sys.argv.index("--items") + 1]

    if not os.path.exists(input_file):
        print(f"错误：输入文件不存在 {input_file}")
        sys.exit(1)
    if not os.path.exists(items_path):
        print(f"错误：清单文件不存在 {items_path}")
        sys.exit(1)

    with open(items_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    author = data.get("author", DEFAULT_AUTHOR)
    items = data.get("items", data if isinstance(data, list) else [])

    doc = Document(input_file)
    mgr = CommentManager(doc)

    results, stats = apply_items(doc, mgr, items, author,
                                 merge_by_clause=data.get("merge_by_clause", False))

    doc.save(output_file)

    print(f"修订批注完成！输出文件: {output_file}")
    print(f"作者署名: {author}")
    print(f"统计: 修订 {stats['revised']} 处 / 批注 {stats['commented']} 条 / 失败 {stats['failed']} 处")
    print("-" * 50)
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
