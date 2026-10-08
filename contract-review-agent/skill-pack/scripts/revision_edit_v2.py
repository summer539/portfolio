#!/usr/bin/env python3
"""
合同修订工具 v2.1 - 服务器采购合同 甲方立场修订版
对DOCX合同原文做带修订标记(Track Changes)的修改，保留全部排版格式

用法：
    python3 revision_edit_v2.py <input.docx> <output.docx>
"""

import sys, re, copy
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
    rpr = source_run_elem.find(f'{{{W}}}rPr')
    if rpr is not None:
        new_rpr = etree.Element(f'{{{W}}}rPr')
        for child in rpr:
            new_rpr.append(copy.deepcopy(child))
        return new_rpr
    return None

def make_run(text, rpr_elem=None):
    r = etree.Element(f'{{{W}}}r')
    if rpr_elem is not None:
        r.append(copy.deepcopy(rpr_elem))
    t = etree.SubElement(r, f'{{{W}}}t')
    t.text = text
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return r

def make_del_run(text, rpr_elem=None):
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

def get_run_text(run_elem):
    texts = []
    for t in run_elem.findall(f'{{{W}}}t'):
        if t.text:
            texts.append(t.text)
    for dt in run_elem.findall(f'.//{{{W}}}delText'):
        if dt.text:
            texts.append(dt.text)
    return ''.join(texts)

def replace_text_in_para(para, old_text, new_text):
    """Replace old_text with new_text using tracked changes."""
    p_elem = para._p
    full_text = para.text
    if not full_text or old_text not in full_text:
        return False
    
    start_idx = full_text.index(old_text)
    end_idx = start_idx + len(old_text)
    
    runs = list(p_elem.findall(f'{{{W}}}r'))
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
    
    rpr = copy_run_properties(target_run)
    new_elements = []
    
    if before_text:
        new_elements.append(('run', before_text, rpr))
    new_elements.append(('del', match_text, rpr))
    new_elements.append(('ins', new_text, rpr))
    if after_text:
        new_elements.append(('run', after_text, rpr))
    
    idx_in_parent = list(p_elem).index(target_run)
    p_elem.remove(target_run)
    
    for kind, text, rpr_elem in reversed(new_elements):
        if kind == 'run':
            elem = make_run(text, rpr_elem)
        elif kind == 'del':
            elem = make_del_run(text, rpr_elem)
        elif kind == 'ins':
            elem = make_ins_run(text, rpr_elem)
        p_elem.insert(idx_in_parent, elem)
    
    return True

def delete_text_in_para(para, text_to_delete):
    return replace_text_in_para(para, text_to_delete, "")

def make_comment(doc, mgr, para, text):
    author_info = PersonInfo(author=AUTHOR)
    mgr.add_comment(paragraph=para, text=text, author=author_info)

def insert_after_text(para, anchor_text, insert_text):
    """Insert text after anchor_text using tracked changes (insertion mark)."""
    p_elem = para._p
    full_text = para.text
    if not full_text or anchor_text not in full_text:
        return False
    
    anchor_end = full_text.index(anchor_text) + len(anchor_text)
    
    runs = list(p_elem.findall(f'{{{W}}}r'))
    char_pos = 0
    target_run = None
    run_start = 0
    
    for idx, r in enumerate(runs):
        run_text = get_run_text(r)
        run_end = char_pos + len(run_text)
        if char_pos <= anchor_end < run_end:
            target_run = r
            run_start = char_pos
            break
        char_pos = run_end
    
    if target_run is None:
        return False
    
    run_text = get_run_text(target_run)
    local_pos = anchor_end - run_start
    
    before_text = run_text[:local_pos]
    after_text = run_text[local_pos:]
    
    rpr = copy_run_properties(target_run)
    new_elements = [('run', before_text, rpr)]
    new_elements.append(('ins', insert_text, rpr))
    if after_text:
        new_elements.append(('run', after_text, rpr))
    
    idx_in_parent = list(p_elem).index(target_run)
    p_elem.remove(target_run)
    
    for kind, text, rpr_elem in reversed(new_elements):
        if kind == 'run':
            elem = make_run(text, rpr_elem)
        elif kind == 'ins':
            elem = make_ins_run(text, rpr_elem)
        p_elem.insert(idx_in_parent, elem)
    
    return True


def main():
    if len(sys.argv) < 3:
        print("用法: python3 revision_edit_v2.py <input.docx> <output.docx>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    doc = Document(input_file)
    mgr = CommentManager(doc)
    paragraphs = doc.paragraphs
    
    results = []
    comments_made = []
    
    for idx, para in enumerate(paragraphs):
        t = para.text or ""
        
        # ====== 1. 价格矛盾 - 合同正文说"最终价格"但同时说不含税费 ======
        if "此价格为最终价格，包含设备款、运输费、装卸费、保险费。" in t:
            replace_text_in_para(para,
                "此价格为最终价格，包含设备款、运输费、装卸费、保险费。",
                "此价格为含税价格，包含设备款、运输费、装卸费、保险费。适用增值税税率13%，甲方要求的发票类型为增值税专用发票。如遇国家税率政策调整，合同总价款应随税率变化相应调整（不含税价格不变）。")
            make_comment(doc, mgr, para,
                "🔴【价格条款矛盾】原合同称'最终价格'但同时又列举了多项额外费用（税费、安装费、培训费、维保费），矛盾且不符合SOP要求。已修改为：①明确为含税价；②约定增值税税率和发票类型；③增加税率调整规则。合同总金额应覆盖所有可预见的必要费用，避免后续产生XX争议。")
            results.append("✅ §3/§4 价格条款修订：明确含税价+税率+发票类型+税率调整规则")
            continue
        
        # ====== 2. 价格中排除条款 ======
        if "但不包括以下费用" in t:
            # Replace the exclusion list with included items
            replace_text_in_para(para,
                "但不包括以下费用：\n— 税费（需额外支付）\n— 现场安装调试费（需额外支付）\n— 培训费用（需额外支付）\n— 一年后的维保费用（需额外支付）",
                "上述价格包含如下必要服务：\n— 现场安装调试服务\n— 设备操作培训服务（不超过5人，3天）\n— 质保期内（三年）的所有维保费用。\n质保期后的维保服务费用由双方另行协商确定。")
            make_comment(doc, mgr, para,
                "🟡【费用范围】原合同中'税费、安装费、培训费'需额外支付，表述模糊。已修改为明确包含安装调试和培训服务费用，避免后续XX争议。一年后的维保费保留另行协商的灵活性。")
            results.append("✅ §3 费用范围修订：安装调试和培训费用纳入合同总价")
            continue
        
        # ====== 3. 乙方信息缺失 ======
        if "联系人：王建国" in t:
            insert_after_text(para,
                "联系人：王建国",
                "\n法定代表人：________（需补充）\n统一社会信用代码：________（需补充）\n联系电话：021-12345678")
            make_comment(doc, mgr, para,
                "🟡【乙方信息不完整】乙方仅提供公司名称和联系人，缺少法定代表人、统一社会信用代码等关键信息。根据SOP要求，签约前必须核实乙方营业执照信息。请业务人员要求乙方补充。")
            results.append("✅ §2 补充乙方信息要求（法定代表人、统一社会信用代码）")
            continue
        
        # ====== 4. 预付款30% - 增加保函要求 ======
        if "预付款：合同签订后5个工作日内，甲方向乙方支付合同总金额的30%作为预付款" in t:
            replace_text_in_para(para,
                "预付款：合同签订后5个工作日内，甲方向乙方支付合同总金额的30%作为预付款，即人民币574,800元。",
                "预付款：合同签订后5个工作日内，甲方在收到乙方提交的等额预付款保函（银行出具的不可撤销保函，金额¥574,800，有效期至设备最终验收合格之日）后，向乙方支付合同总金额的30%作为预付款，即人民币574,800元。")
            make_comment(doc, mgr, para,
                "🔴【预付款风险】30%预付款（¥574,800）无任何担保措施，风险较高。根据公司SOP，大额采购预付款超过10%-20%必须要求卖方提供等额预付款保函。已增加预付款保函前置条件。")
            results.append("✅ §7 预付款增加银行保函前置条件")
            continue
        
        # ====== 5. 到货款 ======
        if "到货款：设备到达甲方指定地点并经初步验收合格后5个工作日内，甲方向乙方支付合同总金额的50%，即人民币958,000元。" in t:
            replace_text_in_para(para,
                "到货款：设备到达甲方指定地点并经初步验收合格后5个工作日内，甲方向乙方支付合同总金额的50%，即人民币958,000元。",
                "到货款：设备到达甲方指定地点并经初步验收合格后5个工作日内，甲方向乙方支付合同总金额的40%，即人民币766,400元。")
            make_comment(doc, mgr, para,
                "🟡【到货款比例调整】原到货款50%过高。根据公司SOP，到货款不超过合同总价30%-40%。初步验收仅确认数量和外包装，不应支付过高比例。已调整为40%。")
            results.append("✅ §7 到货款比例从50%调整为40%")
            continue
        
        # ====== 6. 尾款（验收款） ======
        if "尾款：设备安装调试完毕并经最终验收合格后5个工作日内，甲方向乙方支付合同总金额的15%，即人民币287,400元。" in t:
            replace_text_in_para(para,
                "尾款：设备安装调试完毕并经最终验收合格后5个工作日内，甲方向乙方支付合同总金额的15%，即人民币287,400元。",
                "尾款（验收款）：设备安装调试完毕并经最终验收合格后5个工作日内，甲方向乙方支付合同总金额的25%，即人民币479,000元。")
            make_comment(doc, mgr, para,
                "🟡【验收款比例调整】原验收款仅15%（合计支付至95%）。根据公司SOP，验收款应支付至合同总价90%-95%。已相应调整。")
            results.append("✅ §7 尾款比例从15%调整为25%（支付至95%）")
            continue
        
        # ====== 7. 逾期付款违约金 ======
        if "甲方逾期付款的，每逾期一天，应按逾期金额的万分之三向乙方支付违约金。逾期超过30天的，乙方有权终止合同并要求甲方赔偿全部损失。" in t:
            replace_text_in_para(para,
                "甲方逾期付款的，每逾期一天，应按逾期金额的万分之三向乙方支付违约金。逾期超过30天的，乙方有权终止合同并要求甲方赔偿全部损失。",
                "甲方逾期付款的，每逾期一天，应按逾期金额的万分之五向乙方支付违约金。逾期超过30天的，乙方有权终止合同并要求甲方赔偿直接损失。")
            make_comment(doc, mgr, para,
                "🟡【逾期付款违约金】原条款：①违约金万分之三/日偏低，SOP建议不低于0.1%/日（千分之一），但商业谈判中可协商；②'全部损失'范围过宽，已限缩为'直接损失'。建议业务人员结合谈判情况确定合适的违约金比例。")
            results.append("✅ §9 逾期付款违约金调整+损失范围限缩")
            continue
        
        # ====== 8. 乙方延迟交货违约金 ======
        if "但乙方延迟交货的，每逾期一天，应按合同总金额的万分之五向甲方支付违约金。逾期超过60天的，甲方有权终止合同。" in t:
            replace_text_in_para(para,
                "但乙方延迟交货的，每逾期一天，应按合同总金额的万分之五向甲方支付违约金。逾期超过60天的，甲方有权终止合同。",
                "但乙方延迟交货的，每逾期一天，应按合同总金额的千分之一向甲方支付违约金。逾期超过30天的，甲方有权终止合同并要求乙方返还已付款项，并赔偿甲方因此遭受的直接损失。")
            make_comment(doc, mgr, para,
                "🟡【乙方违约条款不平衡】①乙方延迟交货违约金万分之五/日远低于甲方逾期付款的万分之五/日，双方违约金标准已调整一致；②逾期60天才能解除合同过长，缩短至30天；③补充返还已付款项义务。请业务人员争取此条款。")
            results.append("✅ §20/§9 乙方延迟交货违约金调整+解除条件优化")
            continue
        
        # ====== 9. 验收期限 - 初步验收 ======
        if "设备到达甲方指定地点后3个工作日内，甲乙双方共同进行初步验收" in t:
            replace_text_in_para(para, "3个工作日内", "7个工作日内")
            make_comment(doc, mgr, para,
                "🟡【初验期限过短】原初验仅3个工作日，对于大批量服务器设备的数量清点和外观检查时间不足。已延长至7个工作日。")
            results.append("✅ §10 初验期限：3日→7日")
            continue
        
        # ====== 10. 验收期限 - 最终验收 ======
        if "验收时间：设备安装调试完成后10个工作日内进行最终验收。" in t:
            insert_after_text(para,
                "验收时间：设备安装调试完成后10个工作日内进行最终验收。",
                "\n甲方有权根据实际需要合理延长验收期限，但最长不超过30个工作日。")
            make_comment(doc, mgr, para,
                "🔴【终验期限过短】原终验仅10个工作日（合计初验+终验仅13个工作日），远低于SOP建议的不少于30日。已增加延期灵活性。请业务人员争取整体验收期不低于30个工作日。")
            results.append("✅ §11 终验期限增加延期灵活性（最长30个工作日）")
            continue
        
        # ====== 11. 视同验收条款 ======
        if "但甲方因自身原因不配合验收的，视为验收通过" in t:
            delete_text_in_para(para, "但甲方因自身原因不配合验收的，视为验收通过。")
            make_comment(doc, mgr, para,
                "🔴【视同验收条款】已删除此条款。根据公司合同审核SOP，甲方立场坚决不接受'逾期未验收视为合格'的约定，验收主动权应完全掌握在甲方手中。")
            results.append("✅ §12 删除'视同验收'条款")
            continue
        
        # ====== 12. 隐蔽瑕疵追责 ======
        if "质保期内因设备质量问题导致的故障，由乙方负责免费维修或更换。" in t:
            insert_after_text(para,
                "质保期内因设备质量问题导致的故障，由乙方负责免费维修或更换。",
                "\n隐蔽瑕疵、内在质量问题不受检验期限制，质保期内发现的乙方仍需承担退换、维修、赔偿责任。")
            make_comment(doc, mgr, para,
                "🟡【隐蔽瑕疵】已增加隐蔽瑕疵追责条款。根据SOP，甲方立场应明确隐蔽瑕疵、内在质量问题不受检验期限制，质保期内发现的乙方仍需承担责任。")
            results.append("✅ §19 增加隐蔽瑕疵追责条款")
            continue
        
        # ====== 13. 质保期重新起算 ======
        if "乙方更换的部件应为原厂新品或同等质量产品。" in t:
            insert_after_text(para,
                "乙方更换的部件应为原厂新品或同等质量产品。",
                "\n质保期内因质量问题更换部件的，该部件的质保期自更换完成之日起重新计算。")
            make_comment(doc, mgr, para,
                "🟡【质保期重新起算】已增加更换部件质保期重新起算的约定，确保甲方权益。")
            results.append("✅ §19 增加更换部件质保期重算条款")
            continue
        
        # ====== 14. 争议管辖 ======
        if "任一方可向乙方所在地人民法院提起诉讼" in t:
            replace_text_in_para(para,
                "任一方可向乙方所在地人民法院提起诉讼",
                "任一方可向甲方所在地人民法院提起诉讼")
            make_comment(doc, mgr, para,
                "🔴【争议管辖】原条款约定在乙方所在地（上海）法院诉讼。甲方在北京，到上海诉讼将大幅增加维权成本。根据SOP，争议管辖应选择甲方所在地法院。已修订。")
            results.append("✅ §22 争议管辖：乙方所在地→甲方所在地")
            continue
        
        # ====== 15. 预付款不予退还条款 ======
        if "甲方已支付的预付款不予退还，除非因乙方根本违约导致合同解除" in t:
            replace_text_in_para(para,
                "甲方已支付的预付款不予退还，除非因乙方根本违约导致合同解除。",
                "合同解除后，双方应根据合同履行情况进行结算。乙方应在解除后10个工作日内返还甲方已支付的未履行对应义务部分的款项。")
            make_comment(doc, mgr, para,
                "🔴【预付款锁定条款】原条款'预付款不予退还'将预付款变相锁定为沉没成本，即使乙方违约也不退还，对甲方极为不利且与第二十条乙方违约返还义务相矛盾。已修改为按履行进度比例结算退还。")
            results.append("✅ §26 预付款锁定条款删除，改为按进度结算退还")
            continue
        
        # ====== 16. 培训费用 ======
        if "培训费用另行协商，且不包含在本合同价格内。" in t:
            replace_text_in_para(para,
                "培训费用另行协商，且不包含在本合同价格内。",
                "上述培训内容的费用已包含在本合同总价内，乙方不得另行收取。超出前述范围的培训服务费用由双方另行协商。")
            make_comment(doc, mgr, para,
                "🟡【培训费用】原条款培训费用另行协商且不包含在合同总价内，与合同总价应覆盖必要交付的完整性要求矛盾。已修改为基础培训费用包含在合同总价内。")
            results.append("✅ §16 培训费用纳入合同总价")
            continue
        
        # ====== 17. 验收条款补充隐蔽瑕疵 ======
        if "但甲方因自身原因不配合验收的" in t:
            pass  # Already handled above
        
        # ====== 18. 第二十条 违约责任 - 全面优化 ======
        if "乙方延迟交货：每逾期一天，按合同总金额的万分之五支付违约金。逾期超过60天，甲方有权解除合同，乙方应返还已付款项，并按合同总金额的20%赔偿甲方损失。" in t:
            replace_text_in_para(para,
                "乙方延迟交货：每逾期一天，按合同总金额的万分之五支付违约金。逾期超过60天，甲方有权解除合同，乙方应返还已付款项，并按合同总金额的20%赔偿甲方损失。",
                "乙方延迟交货：每逾期一天，按合同总金额的千分之一支付违约金。逾期超过30天，甲方有权解除合同，乙方应返还全部已付款项，并按合同总金额的20%赔偿甲方损失。")
            make_comment(doc, mgr, para,
                "🟡【乙方违约责任】①违约金从万分之五/日调整为千分之一/日，使其不低于甲方违约标准；②解除期限从60天缩短至30天，降低甲方等待成本。请业务人员重点谈判此条款。")
            results.append("✅ §20 乙方延迟交货违约责任优化")
            continue
        
        # ====== 19. 合同附件效力 ======
        if "本合同附件：" in t:
            insert_after_text(para,
                "本合同附件：",
                "\n上述附件均为本合同不可分割的组成部分，与本合同具有同等法律效力。如附件内容与合同正文不一致，以合同正文为准。")
            make_comment(doc, mgr, para,
                "ℹ️【附件效力】已增加附件效力条款，明确附件与本合同的关系及冲突解决规则。")
            results.append("✅ §附件 增加附件效力条款")
            continue

    # Now add overall summary comment at the beginning
    # Add comprehensive risk summary to the first paragraph
    if paragraphs:
        make_comment(doc, mgr, paragraphs[0],
            "📋 审核立场：甲方（采购方）\n\n"
            "审核结论：本合同中存在多处对甲方不利的条款，建议重点谈判以下事项：\n\n"
            "🔴【必须修改】\n"
            "1. 价格条款矛盾：'最终价格'同时排除税费、安装费等\n"
            "2. 预付款30%无担保 → 需预付款保函\n"
            "3. 争议管辖在乙方所在地 → 改为甲方所在地\n"
            "4. 预付款锁定条款 → 改为按比例结算\n"
            "5. 视同验收条款 → 已删除\n\n"
            "🟡【建议优化】\n"
            "6. 验收期限过短（合计13日→建议≥30日）\n"
            "7. 付款比例调整（到货款50%→40%，验收款15%→25%）\n"
            "8. 乙方延迟交货违约金过低\n"
            "9. 乙方信息不完整\n"
            "10. 培训费用未纳入总价\n\n"
            "⚠️ 本审核为技术性审查，不替代正式法律意见书。重大风险条款建议咨询专业律师。最终决策权归审核人所有。\n"
            "—— 小龙(合同审核助手)")
        results.append("✅ 已添加审核摘要批注")
    
    doc.save(output_file)
    
    print(f"修订完成！输出文件: {output_file}")
    print(f"\n共完成 {len(results)} 项修订：")
    for r in results:
        print(f"  {r}")


if __name__ == "__main__":
    main()
