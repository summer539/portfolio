# -*- coding: utf-8 -*-
import os, sys, json, uuid, io, traceback, zipfile, copy
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(HERE, "_tmp")
os.makedirs(TMP, exist_ok=True)
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XMLNS = "http://www.w3.org/XML/1998/namespace"
def Wq(name): return "{%s}%s" % (W, name)
def ln(el): return etree.QName(el.tag).localname
def gattr(el, name):
    v = el.get(Wq(name))
    if v is None: v = el.get("w:" + name)
    return v

STATE = {}

def all_text(el):
    s = ""
    for t in el.iter():
        n = ln(t)
        if n == "t" or n == "delText":
            s += (t.text or "")
    return s

def parse_comments(cmts):
    if cmts is None: return []
    out = []
    for c in cmts.iter():
        if ln(c) != "comment": continue
        out.append({"id": gattr(c,"id"), "author": gattr(c,"author") or "未知",
                     "date": gattr(c,"date") or "", "text": all_text(c)})
    return out

def parse_revisions(doc):
    out = []
    revmap = {"ins":"新增","del":"删除","moveTo":"移入","moveFrom":"移出"}
    for p in doc.iter():
        if ln(p) != "p": continue
        para_buf = ""
        for el in p.iter():
            if el is p: continue
            n = ln(el)
            if n in revmap:
                nested = False; anc = el.getparent()
                while anc is not None and anc is not p:
                    if ln(anc) == n: nested = True; break
                    anc = anc.getparent()
                if not nested:
                    out.append({"type": n, "label": revmap[n],
                                 "author": gattr(el,"author") or "未知",
                                 "date": gattr(el,"date") or "",
                                 "id": gattr(el,"id") or "",
                                 "text": all_text(el), "pre": para_buf[-20:]})
            elif n == "t":
                para_buf += (el.text or "")
    return out

def para_of(el):
    p = el
    while p is not None:
        if ln(p) == "p": return p
        p = p.getparent()
    return None

def p_text(p):
    if p is None: return ""
    return "".join((t.text or "") for t in p.iter() if ln(t) == "t")

def find_pos(hay, needle):
    """去空白后查找子串，返回原始索引；找不到返回 -1"""
    if not hay or not needle: return -1
    nh = "".join(ch for ch in hay if not ch.isspace())
    nn = "".join(ch for ch in needle if not ch.isspace())
    if not nn: return -1
    i = nh.find(nn)
    if i < 0: return -1
    cnt = 0
    for j, ch in enumerate(hay):
        if not ch.isspace():
            if cnt == i: return j
            cnt += 1
    return -1

def build_comment_meta(doc):
    order = {}; pidx = {}; ranges = {}; refs = {}
    start_para = {}; end_para = {}
    para_texts = []; pcount = [-1]; last = [None]
    active = {}; seq = [0]
    for el in doc.iter():
        n = ln(el)
        pp = para_of(el)
        if pp is not last[0]:
            last[0] = pp; pcount[0] += 1; para_texts.append(p_text(pp))
        if n == "commentRangeStart":
            cid = gattr(el, "id")
            active[cid] = []
            start_para[cid] = pcount[0]
            if cid not in order: order[cid] = seq[0]; seq[0] += 1
            pidx[cid] = pcount[0]; refs[cid] = pp
        elif n == "commentRangeEnd":
            cid = gattr(el, "id")
            if cid in active:
                ranges[cid] = "".join(active[cid])
                end_para[cid] = pcount[0]
                del active[cid]
        elif n == "commentReference":
            cid = gattr(el, "id"); refs[cid] = pp
            if cid not in order: order[cid] = seq[0]; seq[0] += 1
            pidx[cid] = pcount[0]
        elif n in ("t", "delText"):
            for cid in active:
                if len(active[cid]) < 20000: active[cid].append(el.text or "")
    ctx = {}; ctxMeta = {}
    ids = set(list(refs.keys()) + list(ranges.keys()))
    for cid in ids:
        t = ranges.get(cid, "") or (p_text(refs.get(cid)) if refs.get(cid) is not None else "")
        if not t:
            for k in range(pidx.get(cid, -1), -1, -1):
                if k < len(para_texts) and para_texts[k] and para_texts[k].strip():
                    t = para_texts[k]; break
        ctx[cid] = t
        sp = start_para.get(cid, pidx.get(cid, -1))
        ep = end_para.get(cid, sp)
        sp_text = para_texts[sp] if 0 <= sp < len(para_texts) else ""
        ep_text = para_texts[ep] if 0 <= ep < len(para_texts) else ""
        pre = ""; nxt = ""
        if t:
            head = t[:15]; tail = t[-15:]
            pos = find_pos(sp_text, head)
            if pos >= 0: pre = sp_text[max(0, pos-40):pos]
            else: pre = sp_text[-40:] if sp_text else ""
            pos2 = find_pos(ep_text, tail)
            if pos2 >= 0:
                nxt = ep_text[pos2+len(tail):pos2+len(tail)+40]
            else: nxt = ep_text[:40] if ep_text else ""
        else:
            pre = sp_text[-40:] if sp_text else ""
            nxt = ep_text[:40] if ep_text else ""
        # 前后文为空（批注所在段落整段被删除等场景）时，
        # 向前/后找最近的非空段落文本，作为前端定位锚点
        if not pre:
            k = sp - 1
            while k >= 0 and not para_texts[k].strip(): k -= 1
            if k >= 0: pre = para_texts[k][-40:]
        if not nxt:
            k = ep + 1
            while k < len(para_texts) and not para_texts[k].strip(): k += 1
            if k < len(para_texts): nxt = para_texts[k][:40]
        ctxMeta[cid] = {"range": t, "para": ep_text or sp_text,
                        "pre": pre, "next": nxt,
                        "start_para": sp, "end_para": ep}
    return {"ctx": ctx, "order": order, "ctxMeta": ctxMeta}

def renumber_revisions(doc):
    """把所有修订的 w:id 重排为唯一整数，修复 AI 工具产生的重复 id。
    在 /api/open 解析后、deepcopy 之前调用，确保 doc/orig_doc/commentRevs/find_rev 用到的 id 全部唯一一致。"""
    i = [0]
    for el in doc.iter():
        n = ln(el)
        if n in ("ins", "del", "moveTo", "moveFrom"):
            el.set(Wq("id"), str(i[0])); i[0] += 1

def _norm_ws(s):
    return "".join(ch for ch in (s or "") if not ch.isspace())

def build_comment_revs(doc):
    cm = build_comment_meta(doc)
    nctx = {cid: _norm_ws(t) for cid, t in cm["ctx"].items()}
    groups = {}

    active = set()
    cur_para = [None]
    para_seqs = []
    pseq_map = {}

    for el in doc.iter():
        n = ln(el)
        if n == "commentRangeStart":
            cid = gattr(el, "id")
            if cid:
                active.add(cid)
        elif n == "commentRangeEnd":
            cid = gattr(el, "id")
            active.discard(cid)
        elif n == "p":
            if cur_para[0] is not None:
                para_seqs.append((cur_para[0], pseq_map.get(id(cur_para[0]), [])))
            cur_para[0] = el
            pseq_map[id(el)] = []
        elif n in ("ins", "del", "moveTo", "moveFrom"):
            p = cur_para[0]
            if p is not None:
                anc = el.getparent(); nested = False
                while anc is not None and anc is not p:
                    if ln(anc) == n:
                        nested = True; break
                    anc = anc.getparent()
                if not nested:
                    pseq_map[id(p)].append((el, n, frozenset(active)))

    if cur_para[0] is not None:
        para_seqs.append((cur_para[0], pseq_map.get(id(cur_para[0]), [])))

    for para, seq in para_seqs:
        i = 0
        while i < len(seq):
            el, n, act = seq[i]
            pair = [(el, n, act)]
            if i + 1 < len(seq):
                m = seq[i + 1][1]
                if n != m and {n, m} <= {"del", "ins"}:
                    pair.append(seq[i + 1])
                    i += 2
                else:
                    i += 1
            else:
                i += 1

            all_cids = set()
            for _, _, a in pair:
                all_cids |= a
            rids = [gattr(e, "id") or "" for e, _, _ in pair]

            if all_cids:
                for cid in all_cids:
                    for rid in rids:
                        lst = groups.setdefault(cid, [])
                        if rid not in lst:
                            lst.append(rid)
            else:
                texts = [_norm_ws(all_text(e)) for e, _, _ in pair]
                matched = []
                for cid, cr in nctx.items():
                    if not cr:
                        continue
                    for t in texts:
                        if t and (t in cr or cr in t):
                            matched.append(cid); break
                for cid in matched:
                    for rid in rids:
                        lst = groups.setdefault(cid, [])
                        if rid not in lst:
                            lst.append(rid)
    return groups


def find_rev(doc, rid):
    for el in doc.iter():
        n = ln(el)
        if n in ("ins","del","moveTo","moveFrom") and gattr(el,"id") == rid:
            return el
    return None

def unwrap(el, rename_del=False):
    parent = el.getparent()
    if parent is None: return
    idx = parent.index(el)
    children = list(el)
    if rename_del:
        for ch in el.iter():
            if ln(ch) == "delText": ch.tag = Wq("t")
    for i, ch in enumerate(children):
        parent.insert(idx+i, ch)
    parent.remove(el)

def remove_el(el):
    p = el.getparent()
    if p is not None: p.remove(el)

def apply_action(op, rid=None, text=None):
    doc = STATE["doc"]; cmts = STATE["cmts"]
    if op in ("accept","reject"):
        el = find_rev(doc, rid)
        if el is None: return False
        n = ln(el)
        if op == "accept":
            if n in ("ins","moveTo"): unwrap(el)
            else: remove_el(el)
        else:
            if n in ("del","moveFrom"): unwrap(el, rename_del=True)
            else: remove_el(el)
    elif op == "accept_all":
        for el in list(doc.iter()):
            n = ln(el)
            if n in ("ins","moveTo"): unwrap(el)
            elif n in ("del","moveFrom"): remove_el(el)
    elif op == "reject_all":
        for el in list(doc.iter()):
            n = ln(el)
            if n in ("del","moveFrom"): unwrap(el, rename_del=True)
            elif n in ("ins","moveTo"): remove_el(el)
    elif op in ("accept_comment","reject_comment"):
        rev_ids = STATE.get("comment_revs", {}).get(rid, [])
        for rid2 in rev_ids:
            el = find_rev(doc, rid2)
            if el is None: continue
            nn = ln(el)
            if op == "accept_comment":
                if nn in ("ins","moveTo"): unwrap(el)
                else: remove_el(el)
            else:
                if nn in ("del","moveFrom"): unwrap(el, rename_del=True)
                else: remove_el(el)
    elif op == "edit_comment":
        if cmts is None: return False
        target = None
        for c in cmts.iter():
            if ln(c) == "comment" and gattr(c,"id") == rid:
                target = c; break
        if target is None: return False
        for ch in list(target): target.remove(ch)
        p = etree.SubElement(target, Wq("p")); r = etree.SubElement(p, Wq("r"))
        t = etree.SubElement(r, Wq("t")); t.set("{%s}space" % XMLNS, "preserve"); t.text = text or ""
    elif op == "delete_comment":
        if cmts is not None:
            for c in list(cmts.iter()):
                if ln(c) == "comment" and gattr(c,"id") == rid:
                    c.getparent().remove(c)
        for el in list(doc.iter()):
            n = ln(el)
            if n in ("commentRangeStart","commentRangeEnd","commentReference") and gattr(el,"id") == rid:
                el.getparent().remove(el)
    elif op in ("accept_comment", "reject_comment"):
        # rid 此处为批注 id；对该批注名下所有修订一并接受/拒绝
        revs = STATE.get("comment_revs", {}).get(rid, [])
        for rid2 in revs:
            el = find_rev(doc, rid2)
            if el is None: continue
            n = ln(el)
            if op == "accept_comment":
                if n in ("ins", "moveTo"): unwrap(el)
                else: remove_el(el)
            else:
                if n in ("del", "moveFrom"): unwrap(el, rename_del=True)
                else: remove_el(el)
    else:
        return False
    return True

def docx_to_pdf(docx_path, pdf_path, show_markup=True, revisions_view=None):
    import pythoncom
    pythoncom.CoInitialize()
    import win32com.client as win32
    app = None; doc = None
    try:
        for prog in ("Kwps.Application", "Word.Application"):
            try: app = win32.Dispatch(prog); break
            except Exception: app = None
        if app is None: raise RuntimeError("WPS/Word COM 不可用")
        try: app.Visible = False
        except Exception: pass
        doc = app.Documents.Open(os.path.abspath(docx_path), ReadOnly=True)
        try:
            w = doc.ActiveWindow
            # 渲染用 docx 已把修订烘焙为普通文本格式（删除线/下划线），无任何 tracked-change 标记，
            # 关闭修订显示，杜绝右侧修订/批注气泡
            if revisions_view is not None:
                w.View.ShowRevisionsAndComments = True
                w.View.RevisionsView = 1 if revisions_view == "original" else 0
                try: w.View.ShowComments = False
                except Exception: pass
            else:
                w.View.ShowRevisionsAndComments = False
                w.View.RevisionsView = 0
                try: w.View.ShowComments = False
                except Exception: pass
        except Exception: pass
        ok = False
        if hasattr(doc, "ExportAsFixedFormat"):
            try: doc.ExportAsFixedFormat(os.path.abspath(pdf_path), 17); ok = True
            except Exception as e: sys.stderr.write("export err: %s\n" % e)
        if not ok:
            doc.SaveAs2(os.path.abspath(pdf_path), 17)
    finally:
        try:
            if doc: doc.Close(False)
        except Exception: pass
        try:
            if app: app.Quit()
        except Exception: pass
        pythoncom.CoUninitialize()

def clean_for_render(rt):
    for el in list(rt.iter()):
        n = ln(el)
        if n in ("ins","moveTo"): unwrap(el)
        elif n in ("del","moveFrom"): remove_el(el)
        elif n.endswith("PrChange") or n in ("numberingChange","cellIns","cellDel"):
            remove_el(el)
        elif n in ("commentReference","commentRangeStart","commentRangeEnd"):
            remove_el(el)

def reject_all_in(doc):
    for el in list(doc.iter()):
        n = ln(el)
        if n in ("del","moveFrom"): unwrap(el, rename_del=True)
        elif n in ("ins","moveTo"): remove_el(el)

def build_zip_bytes_for(doc_tree, cmts_tree, strip_comment_parts=False):
    src = zipfile.ZipFile(io.BytesIO(STATE["zip_bytes"]))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in src.infolist():
            if strip_comment_parts and "comment" in item.filename.lower():
                continue
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                data = etree.tostring(doc_tree, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif item.filename == "word/comments.xml" and cmts_tree is not None:
                data = etree.tostring(cmts_tree, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif strip_comment_parts and item.filename == "[Content_Types].xml":
                ct = etree.fromstring(data)
                for ov in ct.findall("{http://schemas.openxmlformats.org/package/2006/content-types}Override"):
                    if "comment" in (ov.get("PartName","")).lower():
                        ct.remove(ov)
                data = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif strip_comment_parts and item.filename == "word/_rels/document.xml.rels":
                rels = etree.fromstring(data)
                for rel in rels:
                    if "comment" in (rel.get("Target","")).lower():
                        rels.remove(rel)
                data = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)
            z.writestr(item, data)
    return out.getvalue()

def strip_comment_marks(rt):
    """剥离批注标记（commentReference/commentRangeStart/End）。"""
    for el in list(rt.iter()):
        n = ln(el)
        if n in ("commentReference", "commentRangeStart", "commentRangeEnd"):
            remove_el(el)

# OOXML rPr 子元素的 schema 顺序（只列常用项，用于按序插入）
_RPR_SEQ = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
            "dstrike", "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid",
            "vanish", "webHidden", "color", "spacing", "w", "kern", "position", "sz", "szCs",
            "highlight", "u", "effect", "effectDag", "effectLst", "vertAlign", "rtl", "cs",
            "em", "lang", "eastAsia", "specVanish", "oMath"]

def _ensure_rpr_child(rpr, name):
    ex = rpr.find(Wq(name))
    if ex is not None:
        return ex
    el = etree.SubElement(rpr, Wq(name))
    tidx = _RPR_SEQ.index(name) if name in _RPR_SEQ else len(_RPR_SEQ)
    at = len(rpr)
    for ch in rpr:
        if ch is el:
            continue
        ci = _RPR_SEQ.index(ln(ch)) if ln(ch) in _RPR_SEQ else len(_RPR_SEQ)
        if ci > tidx:
            at = list(rpr).index(ch); break
    if at < len(rpr):
        rpr.remove(el); rpr.insert(at, el)
    return el

def _set_run_fmt(r, strike=False, underline=False, color=None):
    rpr = None
    for ch in r:
        if ln(ch) == "rPr": rpr = ch; break
    if rpr is None:
        rpr = etree.SubElement(r, Wq("rPr"))
        r.insert(0, rpr)   # rPr 必须位于 run 的最前
    if strike:
        _ensure_rpr_child(rpr, "strike")
    if color:
        c = _ensure_rpr_child(rpr, "color"); c.set(Wq("val"), color)
    if underline:
        u = _ensure_rpr_child(rpr, "u"); u.set(Wq("val"), "single")

def bake_revisions(rt):
    """把剩余 ins/del 修订烘焙为普通文本格式后解包：
    删除/moveFrom -> 删除线+红，新增/moveTo -> 下划线+绿。
    去掉所有修订标记后，文档不再含 tracked changes，WPS 无从生成右侧修订气泡。"""
    for el in list(rt.iter()):
        n = ln(el)
        if n in ("del", "moveFrom"):
            for r in el.iter():
                if ln(r) == "r":
                    _set_run_fmt(r, strike=True, color="C0392B")
            unwrap(el, rename_del=True)
        elif n in ("ins", "moveTo"):
            for r in el.iter():
                if ln(r) == "r":
                    _set_run_fmt(r, underline=True, color="1A7F37")
            unwrap(el)


def bake_before_view(rt):
    for el in list(rt.iter()):
        nn = ln(el)
        if nn in ("del","moveFrom"):
            for r in el.iter():
                if ln(r) == "r": _set_run_fmt(r, strike=True, color="C0392B")
            unwrap(el, rename_del=True)
        elif nn in ("ins","moveTo"):
            remove_el(el)

def bake_after_view(rt):
    for el in list(rt.iter()):
        nn = ln(el)
        if nn in ("ins","moveTo"):
            for r in el.iter():
                if ln(r) == "r": _set_run_fmt(r, underline=True, color="1A7F37")
            unwrap(el)
        elif nn in ("del","moveFrom"):
            remove_el(el)

def build_render_bytes():
    rt = copy.deepcopy(STATE["doc"])
    bake_revisions(rt)        # 修订烘焙为行内删除线/下划线，去掉修订标记
    strip_comment_marks(rt)   # 剥离批注标记
    # 清空 comments.xml，避免 WPS 在 PDF 右侧生成批注气泡
    ec = copy.deepcopy(STATE["cmts"]) if STATE.get("cmts") is not None else None
    if ec is not None:
        for c in list(ec):
            ec.remove(c)
    return build_zip_bytes_for(rt, ec)

def _set_run_shading(r, fill):
    """给 run 的 rPr 设置底纹（w:shd），同时移除已有的 w:highlight 避免冲突。
    使用 w:shd 替代 w:highlight，可自定义任意十六进制颜色，更柔和美观。"""
    rpr = None
    for ch in r:
        if ln(ch) == "rPr": rpr = ch; break
    if rpr is None:
        rpr = etree.SubElement(r, Wq("rPr")); r.insert(0, rpr)
    for hl in list(rpr):
        if ln(hl) == "highlight": rpr.remove(hl)
    shd = None
    for ch in rpr:
        if ln(ch) == "shd": shd = ch; break
    if shd is None:
        shd = etree.SubElement(rpr, Wq("shd"))
    shd.set(Wq("val"), "clear")
    shd.set(Wq("color"), "auto")
    shd.set(Wq("fill"), fill)

def apply_revision_highlights(doc):
    """给修订文本加自带底纹高亮：ins/moveTo 绿色、del/moveFrom 红色。
    使用 w:shd（底纹）替代 w:highlight，颜色更柔和美观。
    在 clean_for_render 之前调用，此时 ins/del 元素还在文档树中，
    对修订 run 的 rPr 追加 w:shd，之后 clean_for_render 解包时底纹随 run 保留。"""
    if doc is None: return
    fills = {"ins": "C8E6C9", "del": "FFCDD2", "moveTo": "C8E6C9", "moveFrom": "FFCDD2"}
    for el in doc.iter():
        n = ln(el)
        if n not in fills: continue
        fill = fills[n]
        for r in el.iter():
            if ln(r) != "r": continue
            _set_run_shading(r, fill)

def apply_comment_highlights(doc):
    """在渲染前，给被批注覆盖的文本加柔和黄色底纹（w:shd），由 WPS 排版时自动着色。
    遍历 commentRangeStart/End 之间的 run，给其 rPr 加 <w:shd w:fill="FFF3A0"/>。
    使用底纹替代 w:highlight，颜色更柔和、不刺眼。"""
    if doc is None: return
    active = {}
    for el in doc.iter():
        n = ln(el)
        if n == "commentRangeStart":
            cid = gattr(el, "id")
            if cid not in active: active[cid] = True
        elif n == "commentRangeEnd":
            cid = gattr(el, "id")
            active.pop(cid, None)
        elif n == "r":
            if active:
                _set_run_shading(el, "FFF3A0")

def build_before_bytes():
    rt = copy.deepcopy(STATE["orig_doc"])
    bake_before_view(rt)
    clean_for_render(rt)
    strip_comment_marks(rt)
    return build_zip_bytes_for(rt, None, strip_comment_parts=True)

def build_after_bytes():
    rt = copy.deepcopy(STATE["orig_doc"])
    bake_after_view(rt)
    clean_for_render(rt)
    strip_comment_marks(rt)
    return build_zip_bytes_for(rt, None, strip_comment_parts=True)

def build_original_bytes():
    rt = copy.deepcopy(STATE["orig_doc"])
    apply_revision_highlights(rt)  # original 是"拒绝全部修订后"的原始版，被恢复的 del 文本标红
    reject_all_in(rt); clean_for_render(rt)
    return build_zip_bytes_for(rt, STATE["orig_cmts"])

def convert_to_pdf_bytes(data, revisions_view=None):
    job = uuid.uuid4().hex[:12]
    docx = os.path.join(TMP, job+".docx"); pdf = os.path.join(TMP, job+".pdf")
    with open(docx, "wb") as f: f.write(data)
    docx_to_pdf(docx, pdf, True, revisions_view)
    with open(pdf, "rb") as f: out = f.read()
    for p in (docx, pdf):
        try: os.remove(p)
        except Exception: pass
    return out

def refresh_pdf():
    STATE["pdf"] = convert_to_pdf_bytes(build_render_bytes())

def para_pre(p, target):
    buf = ""
    for el in p.iter():
        if el is target: break
        if ln(el) == "t": buf += (el.text or "")
    return buf[-20:]

def build_diff():
    import re
    cmts = STATE.get("orig_cmts") or STATE.get("cmts")
    if cmts is None: return {"adds":[],"dels":[],"mods":[],"all":[]}
    items = []
    for c in cmts.iter():
        if ln(c) != "comment": continue
        text = all_text(c)
        cid = gattr(c, "id") or ""
        author = gattr(c, "author") or ""
        date = gattr(c, "date") or ""
        marker = '\u3010\u4fee\u8ba2\u6027\u8d28\u3011'
        idx = text.find(marker)
        if idx < 0: continue
        rev_text = text[idx + len(marker):].strip()
        m = re.match('(\u5220\u9664|\u65b0\u589e|\u4fee\u6539)', rev_text)
        if not m: continue
        nature = m.group(1)
        old_text = ""; new_text = ""
        for pm in re.finditer('\{([^}]+)\}[\uff1a:]\s*(.*?)(?=\{[^}]+\}|$)', rev_text, re.DOTALL):
            tag = pm.group(1); val = pm.group(2).strip()
            if tag in ('\u539f\u59cb','\u5220\u9664'): old_text = val
            elif tag in ('\u4fee\u6539','\u65b0\u589e'): new_text = val
        cat_map = {'\u5220\u9664':"del",'\u65b0\u589e':"add",'\u4fee\u6539':"mod"}
        cat = cat_map.get(nature, "mod")
        items.append({"cat":cat,"author":author,"date":date,"old":old_text,"new":new_text,"pre":"","cid":cid})
    adds = [it for it in items if it["cat"] == "add"]
    dels = [it for it in items if it["cat"] == "del"]
    mods = [it for it in items if it["cat"] == "mod"]
    return {"adds":adds,"dels":dels,"mods":mods,"all":items}
def payload():
    cm = build_comment_meta(STATE["doc"])
    return {"comments": parse_comments(STATE["cmts"]),
            "revisions": parse_revisions(STATE["doc"]),
            "ctx": cm["ctx"], "order": cm["order"],
            "ctxMeta": cm["ctxMeta"],
            "commentRevs": STATE.get("comment_revs", {})}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body=b"", ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype+"; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body: self.wfile.write(body)
    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/","/index.html"):
            with open(os.path.join(HERE,"index.html"),"rb") as f: data=f.read()
            self._send(200, data, "text/html"); return
        if u.path == "/api/download":
            if not STATE.get("zip_bytes"): self._send(404, b"no doc"); return
            data = build_render_bytes()
            self.send_response(200)
            self.send_header("Content-Type","application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            self.send_header("Content-Disposition",'attachment; filename="edited.docx"')
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path == "/api/health":
            self._send(200, json.dumps({"ok":True}).encode(), "application/json"); return
        if u.path == "/api/debug":
            info = {}
            if STATE.get("orig_doc"):
                rt1 = copy.deepcopy(STATE["orig_doc"])
                bake_before_view(rt1); clean_for_render(rt1); strip_comment_marks(rt1)
                c1 = sum(1 for e in rt1.iter() if ln(e) in ("ins","del","moveTo","moveFrom","pPrChange","rPrChange"))
                rt2 = copy.deepcopy(STATE["orig_doc"])
                bake_after_view(rt2); clean_for_render(rt2); strip_comment_marks(rt2)
                c2 = sum(1 for e in rt2.iter() if ln(e) in ("ins","del","moveTo","moveFrom","pPrChange","rPrChange"))
                orig = sum(1 for e in STATE["orig_doc"].iter() if ln(e) in ("ins","del","moveTo","moveFrom"))
                info = {"orig_revs":orig, "before_remaining":c1, "after_remaining":c2}
            self._send(200, json.dumps(info).encode(), "application/json"); return
        if u.path == "/api/pdf":
            qs = parse_qs(u.query); mode = (qs.get("mode") or ["final"])[0]
            if mode == "original":
                if not STATE.get("orig_doc"): self._send(404, b"no original"); return
                self._send(200, convert_to_pdf_bytes(build_original_bytes()), "application/pdf"); return
            if mode == "markup_original":
                self._send(200, convert_to_pdf_bytes(build_before_bytes()), "application/pdf"); return
            if mode == "markup_final":
                self._send(200, convert_to_pdf_bytes(build_after_bytes()), "application/pdf"); return
            if not STATE.get("pdf"): self._send(404, b"no pdf"); return
            self._send(200, STATE["pdf"], "application/pdf"); return
        if u.path == "/api/diff":
            self._send(200, json.dumps(build_diff(), ensure_ascii=False).encode(), "application/json"); return
        if u.path == "/api/test-doc":
            # 调试用：返回测试文档字节，便于浏览器自动化加载验证
            p = os.path.join(HERE, "sample-comments.docx")
            if os.path.exists(p):
                with open(p, "rb") as f: data = f.read()
                self.send_response(200)
                self.send_header("Content-Type","application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                self.send_header("Content-Length",str(len(data)))
                self.send_header("Cache-Control","no-store")
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send(404, b"no sample")
            return
        self._send(404, b"not found")
    def do_POST(self):
        u = urlparse(self.path); n = int(self.headers.get("Content-Length",0))
        raw = self.rfile.read(n) if n else b""
        try:
            if u.path == "/api/open":
                STATE["zip_bytes"] = raw
                zf = zipfile.ZipFile(io.BytesIO(raw))
                STATE["doc"] = etree.fromstring(zf.read("word/document.xml"))
                renumber_revisions(STATE["doc"])
                cf = zf.namelist()
                STATE["cmts"] = etree.fromstring(zf.read("word/comments.xml")) if "word/comments.xml" in cf else None
                STATE["orig_doc"] = copy.deepcopy(STATE["doc"])
                STATE["orig_cmts"] = copy.deepcopy(STATE["cmts"])
                STATE["comment_revs"] = build_comment_revs(STATE["orig_doc"])
                refresh_pdf()
                self._send(200, json.dumps(payload(), ensure_ascii=False).encode(), "application/json"); return
            if u.path == "/api/action":
                req = json.loads(raw.decode("utf-8") or "{}")
                ok = apply_action(req.get("op"), req.get("id"), req.get("text"))
                if not ok:
                    self._send(400, json.dumps({"error":"action failed","op":req.get("op")}, ensure_ascii=False).encode(), "application/json"); return
                refresh_pdf()
                self._send(200, json.dumps(payload(), ensure_ascii=False).encode(), "application/json"); return
            self._send(404, b"not found")
        except Exception as e:
            tb = traceback.format_exc(); sys.stderr.write(tb)
            self._send(500, json.dumps({"error":str(e),"trace":tb}, ensure_ascii=False).encode(), "application/json")

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173
    host = "0.0.0.0"   # 监听所有网卡，局域网内其他电脑可访问
    srv = ThreadingHTTPServer((host, port), H)
    import socket
    print("docx viewer (editable) on http://127.0.0.1:%d" % port)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), port, socket.AF_INET, socket.SOCK_STREAM):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and not ip.startswith("169.254"):
                print("  局域网访问: http://%s:%d" % (ip, port))
    except Exception: pass
    try: srv.serve_forever()
    except KeyboardInterrupt: pass