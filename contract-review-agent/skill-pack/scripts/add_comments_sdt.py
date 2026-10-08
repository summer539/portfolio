#!/usr/bin/env python3
"""精准批注工具V4：遍历body全部w:p（含表格内、sdt内容控件内），按子串匹配定位，
   通过拆分run实现字符级精准锚定（批注范围精确包裹匹配文本），
   支持同一段落多个问题、同一问题多处命中（分别批注）。
   作者署名：合同审核助手。批注文本内\\n自动转<w:br/>。"""
import copy, json, re, shutil, sys, zipfile
from lxml import etree
from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx_comments import CommentManager, PersonInfo

XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
TEXT_TAGS = (qn('w:t'), qn('w:br'), qn('w:tab'), qn('w:cr'), qn('w:noBreakHyphen'), qn('w:softHyphen'))

def full_text(p_el):
    return ''.join(t.text or '' for t in p_el.iter(qn('w:t')))

def locate(p_el, match):
    """返回 (ts, si, soff, ei, eoff)：match在段落w:t序列中的起止位置（字符级）"""
    ts = list(p_el.iter(qn('w:t')))
    texts = [t.text or '' for t in ts]
    full = ''.join(texts)
    pos = full.find(match)
    if pos == -1:
        return None
    acc = 0
    si = 0
    soff = 0
    for i, tx in enumerate(texts):
        if acc + len(tx) > pos:
            si = i
            soff = pos - acc
            break
        acc += len(tx)
    epos = pos + len(match)
    acc2 = pos - soff  # si之前的总长度（全局基准）
    ei = si
    eoff = len(texts[si])
    for i in range(si, len(texts)):
        if acc2 + len(texts[i]) >= epos:
            ei = i
            eoff = epos - acc2
            break
        acc2 += len(texts[i])
    return ts, si, soff, ei, eoff

def make_run(r_el, text):
    """复制r_el格式（保留rPr），创建只含text的新run"""
    new_r = copy.deepcopy(r_el)
    for child in list(new_r):
        if child.tag in TEXT_TAGS:
            new_r.remove(child)
    t = etree.SubElement(new_r, qn('w:t'))
    if text != text.strip():
        t.set(XML_SPACE, 'preserve')
    t.text = text
    return new_r

def split_runs_for_anchor(ts, si, soff, ei, eoff):
    """拆分run使match文本独立，返回锚定范围的(首run, 尾run)"""
    t_a, t_b = ts[si], ts[ei]
    if si == ei:
        r_el = t_a.getparent()
        text = t_a.text or ''
        t_a.text = text[soff:eoff]
        if soff > 0:
            r_el.addprevious(make_run(r_el, text[:soff]))
        if eoff < len(text):
            r_el.addnext(make_run(r_el, text[eoff:]))
        return r_el, r_el
    r_a, r_b = t_a.getparent(), t_b.getparent()
    text_a = t_a.text or ''
    if soff > 0:
        tail = text_a[soff:]
        t_a.text = text_a[:soff]
        r_a2 = make_run(r_a, tail)
        r_a.addnext(r_a2)
        start_r = r_a2
    else:
        start_r = r_a
    text_b = t_b.text or ''
    if eoff < len(text_b):
        head = text_b[:eoff]
        t_b.text = text_b[eoff:]
        r_b1 = make_run(r_b, head)
        r_b.addprevious(r_b1)
        end_r = r_b1
    else:
        end_r = r_b
    return start_r, end_r

def find_anchors(p_el, cid):
    rs = re_ = rf = None
    for el in p_el.iter():
        if el.tag == qn('w:commentRangeStart') and el.get(qn('w:id')) == cid:
            rs = el
        elif el.tag == qn('w:commentRangeEnd') and el.get(qn('w:id')) == cid:
            re_ = el
        elif el.tag == qn('w:commentReference') and el.get(qn('w:id')) == cid:
            rf = el.getparent()
    return rs, re_, rf

def locate_blank_sdt(root, alias):
    """按sdt alias定位空白填写处（如计量单位空白单元格），返回(所在w:p, sdt元素)；未找到返回None。
    锚定目标是sdt本身（即空白填写位置），而非表头/标签文字。"""
    for sdt in root.iter(qn('w:sdt')):
        pr = sdt.find(qn('w:sdtPr'))
        if pr is None:
            continue
        al = pr.find(qn('w:alias'))
        if al is not None and al.get(qn('w:val')) == alias:
            p_el = sdt.getparent()
            while p_el is not None and p_el.tag != qn('w:p'):
                p_el = p_el.getparent()
            if p_el is not None:
                return p_el, sdt
    return None

def fix_newlines(docx_path):
    """把comments.xml中w:t内的\\n转为<w:br/>（与w:t平级），确保Word中批注正确换行且XML结构合法"""
    tmp = docx_path + ".tmp"
    with zipfile.ZipFile(docx_path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item == "word/comments.xml":
                text = data.decode("utf-8")
                text = re.sub(
                    r"(<w:t[^>]*>)([^<]*?)(</w:t>)",
                    lambda m: m.group(1) + m.group(2).replace("\n", "</w:t><w:br/><w:t>") + m.group(3),
                    text,
                )
                data = text.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, docx_path)

def main(inp, outp, anns):
    doc = Document(inp)
    mgr = CommentManager(doc)
    author = PersonInfo(author="合同审核助手")
    paras = [Paragraph(p_el, doc.element.body) for p_el in doc.element.body.iter(qn('w:p'))]
    anchored = {}  # w:t元素 -> set(已批注的match文本)；按(元素,批注项)粒度去重，同元素不同区域的问题可分别批注
    ok = fail = 0
    for ann in anns:
        text = ann["text"]
        # 模式一：空白填写处锚定（按sdt alias定位，锚点=空白sdt本身，光标落在空白处而非表头）
        if ann.get("alias"):
            loc = locate_blank_sdt(doc.element.body, ann["alias"])
            if loc is None:
                print(f"[未找到] sdt alias={ann['alias']}", file=sys.stderr)
                fail += 1
                continue
            p_el, sdt_el = loc
            p_obj = next((p for p in paras if p._p is p_el), None)
            if p_obj is None:
                print(f"[未找到] 段落对象 alias={ann['alias']}", file=sys.stderr)
                fail += 1
                continue
            temp_run = etree.Element(qn('w:r'))  # 临时空run，供add_comment的add_anchors定位
            sdt_el.addnext(temp_run)
            try:
                cid = mgr.add_comment(paragraph=p_obj, text=text, author=author, start_run=0, end_run=0)
                rng_start, rng_end, ref_run = find_anchors(p_el, cid)
                if rng_start is None or rng_end is None or ref_run is None:
                    p_el.remove(temp_run)
                    fail += 1
                    continue
                sdt_el.addprevious(rng_start)   # 锚点起点：空白sdt之前（即空白填写处起始）
                sdt_el.addnext(rng_end)         # 锚点终点：空白sdt之后
                rng_end.addnext(ref_run)        # 批注引用标记紧随其后
                p_el.remove(temp_run)
                ok += 1
            except Exception as e:
                print(f"[异常] alias={ann['alias']}: {e}", file=sys.stderr)
                if temp_run.getparent() is not None:
                    p_el.remove(temp_run)
                fail += 1
            continue
        # 模式二：文本子串精准锚定
        match = ann["match"]
        hit_any = False
        for p in paras:
            loc = locate(p._p, match)
            if loc is None:
                continue
            ts, si, soff, ei, eoff = loc
            if all(t in anchored and match in anchored[t] for t in ts[si:ei + 1]):
                continue  # 同一批注项在该文本区域已批注（内外层重复），跳过
            start_r, end_r = split_runs_for_anchor(ts, si, soff, ei, eoff)
            cid = mgr.add_comment(paragraph=p, text=text, author=author, start_run=0, end_run=0)
            rng_start, rng_end, ref_run = find_anchors(p._p, cid)
            if rng_start is None or rng_end is None or ref_run is None:
                fail += 1
                continue
            start_r.addprevious(rng_start)
            end_r.addnext(rng_end)
            rng_end.addnext(ref_run)
            for t in ts[si:ei + 1]:
                anchored.setdefault(t, set()).add(match)
            ok += 1
            hit_any = True
        if not hit_any:
            print(f"[未找到] {match}", file=sys.stderr)
            fail += 1
    doc.save(outp)
    fix_newlines(outp)
    print(f"完成：成功 {ok} 条，失败 {fail} 条 -> {outp}")

if __name__ == "__main__":
    inp, outp, annfile = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(annfile, encoding="utf-8") as f:
        anns = json.load(f)
    main(inp, outp, anns)
