#!/usr/bin/env python3
"""
合同修订工具 v2 - 保留原格式的修订+批注版
对DOCX合同原文做带修订标记(Track Changes)的修改，同时保留全部排版格式

用法：
    python3 revision_edit.py <input.docx> <output.docx>

依赖：python-docx, docx-comments, lxml
"""

import sys
import re
import copy
from datetime import datetime
from lxml import etree
from docx import Document
from docx_comments import CommentManager, PersonInfo

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
AUTHOR = "小龙(合同审核助手)"
REV_ID = [999]

def next_id():
    REV_ID[0] += 1
    return REV_ID[0]

def now_str():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

def copy_run_properties(source_run_elem):
    """Copy w:rPr from source run element to a new rPr element."""
    rpr = source_run_elem.find(f'{{{W}}}rPr')
    if rpr is not None:
        new_rpr = etree.Element(f'{{{W}}}rPr')
        for child in rpr:
            new_rpr.append(copy.deepcopy(child))
        return new_rpr
    return None

def make_run(text, rpr_elem=None):
    """Create a w:r element with optional rPr."""
    r = etree.Element(f'{{{W}}}r')
    if rpr_elem is not None:
        r.append(copy.deepcopy(rpr_elem))
    t = etree.SubElement(r, f'{{{W}}}t')
    t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return r

def make_del_run(text, rpr_elem=None):
    """Create w:del containing w:r with w:delText."""
    del_elem = etree.Element(f'{{{W}}}del')
    del_elem.set(f'{{{W}}}id', str(next_id()))
    del_elem.set(f'{{{W}}}author', AUTHOR)
    del_elem.set(f'{{{W}}}date', now_str())
    r = etree.Element(f'{{{W}}}r')
    if rpr_elem is not None:
        r.append(copy.deepcopy(rpr_elem))
    dt = etree.SubElement(r, f'{{{W}}}delText')
    dt.text = text
    dt.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    del_elem.append(r)
    return del_elem

def make_ins_run(text, rpr_elem=None):
    """Create w:ins containing w:r with w:t."""
    ins_elem = etree.Element(f'{{{W}}}ins')
    ins_elem.set(f'{{{W}}}id', str(next_id()))
    ins_elem.set(f'{{{W}}}author', AUTHOR)
    ins_elem.set(f'{{{W}}}date', now_str())
    r = etree.Element(f'{{{W}}}r')
    if rpr_elem is not None:
        r.append(copy.deepcopy(rpr_elem))
    t = etree.SubElement(r, f'{{{W}}}t')
    t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    ins_elem.append(r)
    return ins_elem

def replace_text_in_para(para, old_text, new_text):
    """
    Replace old_text with new_text in a paragraph, preserving formatting.
    Uses tracked changes (w:del + w:ins).
    Returns True if found and replaced.
    """
    p_elem = para._p
    full_text = para.text
    if not full_text or old_text not in full_text:
        return False
    
    # Find which run contains the old text by reconstructing
    runs = list(p_elem.findall(f'{{{W}}}r'))
    
    # Get the start position of old_text in the full text
    start_idx = full_text.index(old_text)
    end_idx = start_idx + len(old_text)
    
    # Track character positions across runs
    char_pos = 0
    target_run = None
    target_run_idx = -1
    run_start = 0
    
    for idx, r in enumerate(runs):
        run_text = get_run_text(r)
        run_end = char_pos + len(run_text)
        
        if char_pos <= start_idx < run_end:
            target_run = r
            target_run_idx = idx
            run_start = char_pos
            break
        char_pos = run_end
    
    if target_run is None:
        return False
    
    run_text = get_run_text(target_run)
    local_start = start_idx - run_start
    local_end = end_idx - run_start
    
    before_text = run_text[:local_start]
    match_text = run_text[local_start:local_end]
    after_text = run_text[local_end:]
    
    # Get run properties from the original run
    rpr = copy_run_properties(target_run)
    
    # Build new elements
    new_elements = []
    
    # Text before match (unchanged)
    if before_text:
        new_elements.append(('run', before_text, rpr))
    
    # Deleted text
    new_elements.append(('del', match_text, rpr))
    
    # Inserted text
    new_elements.append(('ins', new_text, rpr))
    
    # Text after match (unchanged)
    if after_text:
        new_elements.append(('run', after_text, rpr))
    
    # Replace the target run with new elements
    idx_in_parent = list(p_elem).index(target_run)
    
    # Remove the target run
    p_elem.remove(target_run)
    
    # Insert new elements at the same position
    for kind, text, rpr_elem in reversed(new_elements):
        if kind == 'run':
            elem = make_run(text, rpr_elem)
        elif kind == 'del':
            elem = make_del_run(text, rpr_elem)
        elif kind == 'ins':
            elem = make_ins_run(text, rpr_elem)
        
        p_elem.insert(idx_in_parent, elem)
    
    return True


def get_run_text(run_elem):
    """Get the text content of a w:r element."""
    texts = []
    for t in run_elem.findall(f'{{{W}}}t'):
        if t.text:
            texts.append(t.text)
    # Also check delText for already-revised content
    for dt in run_elem.findall(f'.//{{{W}}}delText'):
        if dt.text:
            texts.append(dt.text)
    return ''.join(texts)


def delete_text_in_para(para, text_to_delete):
    """Delete specific text with tracked changes, preserving formatting."""
    return replace_text_in_para(para, text_to_delete, "")


def insert_after_text(para, anchor_text, insert_text):
    """
    Insert text after anchor_text in a paragraph.
    Since insert_after is complex with formatting preservation,
    we use a trick: replace anchor_text with anchor_text + insert_text
    with tracked insertion for the insert_text portion.
    
    Actually, let's use replace: find a unique suffix and replace with that + insert.
    """
    full_text = para.text
    if not full_text or anchor_text not in full_text:
        return False
    
    idx = full_text.index(anchor_text) + len(anchor_text)
    
    # We need to insert at position idx
    # Use replace_text_in_para with an empty string replacement trick
    # Simpler: replace a known text at the boundary
    # Find the next 5 chars after anchor_text
    remainder = full_text[idx:]
    
    if not remainder:
        # anchor is at end, append
        return replace_text_in_para(para, anchor_text, anchor_text + insert_text)
    
    # Use first char of remainder as anchor
    next_char = remainder[0]
    search = anchor_text + next_char
    replacement = anchor_text + insert_text + next_char
    return replace_text_in_para(para, search, replacement)


def make_comment(doc, mgr, para, text):
    """Add a comment to a paragraph."""
    author_info = PersonInfo(author=AUTHOR)
    mgr.add_comment(paragraph=para, text=text, author=author_info)


def main():
    if len(sys.argv) < 3:
        print("用法: python3 revision_edit.py <input.docx> <output.docx>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    doc = Document(input_file)
    mgr = CommentManager(doc)
    paragraphs = doc.paragraphs
    
    results = []
    
    # Pre-collect all payment-related replacements for paragraph 26
    payment_replacements = {
        "prepay": {
            "old": "甲方向乙方支付合同总金额的30%作为预付款，即人民币574,800元。",
            "new": "甲方向乙方支付合同总金额的30%作为预付款，即人民币574,800元。乙方应在收款前向甲方提供银行出具的等额预付款保函（金额¥574,800），保函有效期应覆盖至设备最终验收合格之日。"
        },
        "delivery": {
            "old": "到货款：设备到达甲方指定地点并经初步验收合格后5个工作日内，甲方向乙方支付合同总金额的50%，即人民币958,000元。",
            "new": "到货款：设备到达甲方指定地点并经初步验收合格后，且甲方收到下游客户同比例回款后5个工作日内，甲方向乙方支付合同总金额的50%，即人民币958,000元。"
        },
        "final": {
            "old": "尾款：设备安装调试完毕并经最终验收合格后5个工作日内，甲方向乙方支付合同总金额的15%，即人民币287,400元。",
            "new": "尾款：设备安装调试完毕并经最终验收合格后，且甲方收到下游客户同比例回款后5个工作日内，甲方向乙方支付合同总金额的15%，即人民币287,400元。"
        },
        "warranty": {
            "old": "质保金：合同总金额的5%（人民币95,800元），验收合格后一年若无质量问题，一次性无息支付。",
            "new": "质保金：合同总金额的5%（人民币95,800元），甲方收到下游客户同比例回款后，且验收合格后一年若无质量问题，一次性无息支付。"
        }
    }
    
    for para in paragraphs:
        t = para.text or ""
        
        # ====== Payment clause (all items in one paragraph) ======
        if "预付款：合同签订后5个工作日内" in t:
            payment_comments = []
            for key, repl in payment_replacements.items():
                if repl["old"] in t:
                    replace_text_in_para(para, repl["old"], repl["new"])
                    payment_comments.append(key)
            
            if "prepay" in payment_comments:
                make_comment(doc, mgr, para, "🔴【预付款风险】30%预付款（¥574,800）无任何担保措施。已增加预付款保函要求。根据公司SOP，大额采购必须要求卖方提供等额预付款保函/履约保函。")
                results.append("✅ §7 预付款增加保函要求")
            if "delivery" in payment_comments:
                results.append("✅ §7 到货款增加背靠背付款条件")
            if "final" in payment_comments:
                results.append("✅ §7 尾款增加背靠背付款条件")
            if "warranty" in payment_comments:
                results.append("✅ §7 质保金增加背靠背付款条件")
            if len(payment_comments) > 0:
                make_comment(doc, mgr, para, "🟡【背靠背付款】已对到货款、尾款、质保金增加'甲方收到下游客户同比例回款后'的前置条件。根据公司SOP，甲方采购应采用背靠背付款，降低资金风险。")
            continue
        
        # ====== 1. 争议管辖 ======
        if "向乙方所在地人民法院提起诉讼" in t:
            if replace_text_in_para(para, "向乙方所在地人民法院提起诉讼", "向甲方所在地人民法院提起诉讼"):
                make_comment(doc, mgr, para, "🔴【争议管辖】原条款约定在乙方所在地（上海）诉讼，对甲方极为不利。已修订为甲方所在地法院，大幅降低维权成本。")
                results.append("✅ §22 争议管辖：乙方所在地→甲方所在地")
            continue
        
        # ====== 2. 删除视同验收 ======
        if "但甲方因自身原因不配合验收的，视为验收通过" in t:
            if delete_text_in_para(para, "但甲方因自身原因不配合验收的，视为验收通过。"):
                make_comment(doc, mgr, para, "🔴【视同验收】已删除此条款。根据公司合同审核SOP，甲方立场不接受'逾期未验收视为合格'的约定，验收主动权应完全掌握在甲方手中。")
                results.append("✅ §12 删除'视同验收'条款")
            continue
        
        # ====== 3. 初验期限 ======
        if "设备到达甲方指定地点后3个工作日内" in t:
            if replace_text_in_para(para, "3个工作日内", "10个工作日内"):
                make_comment(doc, mgr, para, "🟡【验收期限】原初验仅3个工作日，时间过短。已延长至10个工作日，确保甲方有充足时间进行数量清点和外观检查。")
                results.append("✅ §10 初验期限: 3日→10日")
            continue
        
        # ====== 4. 终验期限 ======
        if "设备安装调试完成后10个工作日内进行最终验收" in t:
            if replace_text_in_para(para, "10个工作日内进行最终验收", "20个工作日内进行最终验收"):
                make_comment(doc, mgr, para, "🟡【验收期限】原终验仅10个工作日（合计仅13个工作日），远低于公司SOP要求的≥30日。已延长至20个工作日，确保甲方有充分时间进行全面性能测试。")
                results.append("✅ §11 终验期限: 10日→20日")
            continue
        
        # ====== 9. 预付款退还 ======
        if "甲方已支付的预付款不予退还，除非因乙方根本违约导致合同解除" in t:
            if replace_text_in_para(para,
                "甲方已支付的预付款不予退还，除非因乙方根本违约导致合同解除。",
                "合同解除后，乙方应在10个工作日内返还甲方已支付的全部款项（可扣除已交付合格设备对应比例部分）。"):
                make_comment(doc, mgr, para, "🔴【预付款锁定】原条款将预付款变相锁定为'除非乙方根本违约否则不退'，对甲方极为不利。已修改为合同解除后按比例退还。")
                results.append("✅ §26 预付款退还条款修订")
            continue
        
        # ====== 10. 隐蔽瑕疵 ======
        if "质保期内因设备质量问题导致的故障，由乙方负责免费维修或更换。" in t:
            insert = "\n隐蔽瑕疵、内在质量问题不受检验期限制，质保期内发现的，乙方仍需承担退换、维修、赔偿责任。"
            if insert_after_text(para, "质保期内因设备质量问题导致的故障，由乙方负责免费维修或更换。", insert):
                make_comment(doc, mgr, para, "🟡【隐蔽瑕疵】已增加隐蔽瑕疵追责条款。根据公司SOP，甲方立场应明确隐蔽瑕疵、内在质量问题不受检验期限制。")
                results.append("✅ §19 增加隐蔽瑕疵追责条款")
            continue
        
        # ====== 11. 全部损失→直接损失 ======
        if "逾期超过30天的，乙方有权终止合同并要求甲方赔偿全部损失" in t:
            if replace_text_in_para(para, "赔偿全部损失", "赔偿直接损失"):
                make_comment(doc, mgr, para, "🟡【损失范围】原条款'全部损失'范围过宽，可能包含间接损失、预期利益等。已限缩为'直接损失'，控制甲方违约风险。")
                results.append("✅ §9 全部损失→直接损失")
            continue
    
    doc.save(output_file)
    
    print(f"修订完成！输出文件: {output_file}")
    print(f"\n共完成 {len(results)} 项修订：")
    for r in results:
        print(f"  {r}")


if __name__ == "__main__":
    main()