#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排产审批结果导出为 Excel
基于营销中心原始表格，向右扩展审批建议列
"""
import xlrd
from xlwt import Workbook, XFStyle, Font, Alignment, Borders, Pattern, easyxf
import os


def export_ruling_xls(results, output_path, template_path=None, title=None):
    """
    将审批结果输出为 xls 文件。

    参数:
      results: list[dict], 每项审批结果，每个 dict 包含:
        - brand:       品牌
        - code:        编码
        - spec:        规格
        - process:     工艺
        - excel_sales: Excel 中的销量（原始列）
        - excel_inv:   Excel 中的库存（原始列）
        - M:           营销建议排产量（原始列）
        - remark:      备注（原始列）
        - s_cycle:     金蝶近7天销量
        - inventory:   金蝶实时库存
        - gap:         库存缺口
        - P:           审批建议排产量
        - verdict:     审批结果（✅ 批准 / ⚠️ 建议上调至XX箱 / ⚠️ 偏高待确认）
        - reason:      审批说明
        - trend:       趋势（↑/↓/→）
        - season_cap:  季节上限
        - is_subtotal: 是否小计/总计行
      output_path:  输出文件路径（.xls）
      template_path: 可选，参考模板路径（用于读取标题等）
      title:        可选，表格标题
    """
    wb = Workbook(encoding='utf-8')
    ws = wb.add_sheet('排产审批结果')

    # ── 样式 ──
    header_style = easyxf(
        'font: bold on, height 220;'
        'alignment: horiz centre, vert centre, wrap on;'
        'borders: left thin, right thin, top thin, bottom thin;'
        'pattern: pattern solid, fore_colour light_green;'
    )
    verdict_approve = easyxf(
        'font: bold on, colour green;'
        'alignment: horiz centre, vert centre, wrap on;'
        'borders: left thin, right thin, top thin, bottom thin;'
    )
    verdict_warn = easyxf(
        'font: bold on, colour orange;'
        'alignment: horiz centre, vert centre, wrap on;'
        'borders: left thin, right thin, top thin, bottom thin;'
    )
    normal_style = easyxf(
        'alignment: horiz centre, vert centre, wrap on;'
        'borders: left thin, right thin, top thin, bottom thin;'
    )
    number_style = easyxf(
        'alignment: horiz centre, vert centre;'
        'borders: left thin, right thin, top thin, bottom thin;'
        'font: height 200;'
    )
    title_style = easyxf(
        'font: bold on, height 280;'
        'alignment: horiz centre, vert centre;'
    )
    subtotal_style = easyxf(
        'font: bold on, height 200;'
        'alignment: horiz centre, vert centre;'
        'borders: left thin, right thin, top thin, bottom thin;'
        'pattern: pattern solid, fore_colour light_yellow;'
    )

    # ── 列定义 ──
    # 左侧：营销中心原始列
    orig_cols = ['品牌', '编码', '规格', '工艺', '营销中心报表\n销量/箱', '营销中心报表\n库存/箱', '营销建议\n排产量（箱）', '备注']
    # 右侧：审批扩展列
    ruling_cols = [
        '金蝶上个月\n销量（箱）', '金蝶近7天\n销量（箱）', '金蝶实时\n库存（箱）', '库存缺口\n（箱）',
        '龙工建议\n排产量（箱）', '销量趋势', '审批结果', '审批说明'
    ]

    all_cols = orig_cols + ruling_cols
    n_orig = len(orig_cols)

    # ── 写入标题行 ──
    title_text = title or '排产审批报告'
    ws.write_merge(0, 0, 0, len(all_cols) - 1, title_text, title_style)

    # ── 写表头 ──
    header_row = 1
    for ci, col_name in enumerate(all_cols):
        ws.write(header_row, ci, col_name, header_style)
    # 设置行高
    ws.row(header_row).height_mismatch = True
    ws.row(header_row).height = 600

    # ── 写数据 ──
    row_idx = header_row + 1

    for item in results:
        # 原始列
        ws.write(row_idx, 0, item.get('brand', ''), normal_style)
        ws.write(row_idx, 1, item.get('code', ''), normal_style)
        ws.write(row_idx, 2, item.get('spec', ''), normal_style)
        ws.write(row_idx, 3, item.get('process', ''), normal_style)

        # Excel 销量
        es = item.get('excel_sales', '')
        if es != '' and es is not None and es != '-':
            try:
                ws.write(row_idx, 4, round(float(es), 1), number_style)
            except (ValueError, TypeError):
                ws.write(row_idx, 4, str(es), normal_style)
        else:
            ws.write(row_idx, 4, '', normal_style)

        # Excel 库存
        ei = item.get('excel_inv', '')
        if ei != '' and ei is not None and ei != '-':
            try:
                ws.write(row_idx, 5, round(float(ei), 1), number_style)
            except (ValueError, TypeError):
                ws.write(row_idx, 5, str(ei), normal_style)
        else:
            ws.write(row_idx, 5, '', normal_style)

        # 营销建议 M
        m_val = item.get('M', '')
        if isinstance(m_val, (int, float)):
            ws.write(row_idx, 6, round(m_val, 0), number_style)
        else:
            ws.write(row_idx, 6, str(m_val) if m_val else '', normal_style)

        # 备注
        ws.write(row_idx, 7, item.get('remark', ''), normal_style)

        # 审批扩展列
        if item.get('is_subtotal'):
            # 小计/总计行：只写合计值到龙工建议列
            p_val = item.get('P', '')
            for ci in range(n_orig, len(all_cols)):
                if ci == n_orig + 4 and p_val != '':
                    ws.write(row_idx, ci, str(p_val), subtotal_style)
                else:
                    ws.write(row_idx, ci, '', subtotal_style)
        else:
            # 金蝶上个月销量
            ms = item.get('month_sales', '')
            if isinstance(ms, (int, float)) and ms > 0:
                ws.write(row_idx, n_orig, round(ms, 1), number_style)
            elif ms == 0:
                ws.write(row_idx, n_orig, 0, number_style)
            else:
                ws.write(row_idx, n_orig, str(ms) if ms else '', normal_style)

            # 金蝶近7天销量
            sc = item.get('s_cycle', '')
            if isinstance(sc, (int, float)) and sc > 0:
                ws.write(row_idx, n_orig + 1, round(sc, 1), number_style)
            elif sc == 0:
                ws.write(row_idx, n_orig + 1, 0, number_style)
            else:
                ws.write(row_idx, n_orig + 1, str(sc) if sc else '', normal_style)

            # 金蝶实时库存
            inv = item.get('inventory', '')
            if isinstance(inv, (int, float)):
                ws.write(row_idx, n_orig + 2, round(inv, 1), number_style)
            else:
                ws.write(row_idx, n_orig + 2, str(inv) if inv else '', normal_style)

            # 库存缺口
            gap = item.get('gap', '')
            if isinstance(gap, (int, float)):
                ws.write(row_idx, n_orig + 3, round(gap, 1), number_style)
            else:
                ws.write(row_idx, n_orig + 3, str(gap) if gap else '', normal_style)

            # 龙工建议 P
            p_val = item.get('P', '')
            if isinstance(p_val, (int, float)):
                ws.write(row_idx, n_orig + 4, round(p_val, 0), number_style)
            else:
                ws.write(row_idx, n_orig + 4, str(p_val) if p_val else '', normal_style)

            # 趋势
            ws.write(row_idx, n_orig + 5, item.get('trend', ''), normal_style)

            # 审批结果
            verdict = item.get('verdict', '')
            if '批准' in str(verdict):
                ws.write(row_idx, n_orig + 6, str(verdict), verdict_approve)
            elif '上调' in str(verdict) or '调低' in str(verdict):
                ws.write(row_idx, n_orig + 6, str(verdict), verdict_warn)
            else:
                ws.write(row_idx, n_orig + 6, str(verdict), normal_style)

            # 审批说明
            ws.write(row_idx, n_orig + 7, item.get('reason', ''), normal_style)

        row_idx += 1

    # ── 汇总行 ──
    row_idx += 1
    ws.write_merge(row_idx, row_idx, 0, len(all_cols) - 1, '', normal_style)
    row_idx += 1

    # 统计
    approved = sum(1 for r in results if '批准' in str(r.get('verdict', '')) 
                   and '调低' not in str(r.get('verdict', ''))
                   and '上调' not in str(r.get('verdict', ''))
                   and not r.get('is_subtotal'))
    suggested = sum(1 for r in results if '上调' in str(r.get('verdict', '')) and not r.get('is_subtotal'))
    lowered = sum(1 for r in results if '调低' in str(r.get('verdict', '')) and not r.get('is_subtotal'))

    total_m = sum(r.get('M', 0) for r in results if isinstance(r.get('M'), (int, float)) and not r.get('is_subtotal'))
    total_p = sum(r.get('P', 0) for r in results if isinstance(r.get('P'), (int, float)) and not r.get('is_subtotal'))

    summary_style = easyxf(
        'font: bold on, height 220;'
        'alignment: horiz left, vert centre;'
    )

    ws.write_merge(row_idx, row_idx, 0, len(all_cols) - 1, 
                   f'✅ 批准: {approved} 项    ⚠️ 建议上调: {suggested} 项    ⚠️ 建议调低: {lowered} 项',
                   summary_style)
    row_idx += 1

    if total_m > 0:
        diff_pct = (total_p - total_m) / total_m * 100
        ws.write_merge(row_idx, row_idx, 0, len(all_cols) - 1,
                       f'营销总报: {total_m:.0f} 箱  →  龙工建议: {total_p:.0f} 箱  (变化 {diff_pct:+.1f}%)',
                       summary_style)

    # ── 列宽 ──
    col_widths = [8, 14, 10, 8, 12, 12, 10, 12, 12, 12, 12, 10, 10, 6, 16, 35]
    for ci, w in enumerate(col_widths):
        ws.col(ci).width = int(w * 256 * 1.5)

    # ── 保存 ──
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    wb.save(output_path)
    print(f'审批报告已导出到: {output_path}')
    return output_path


def build_results_from_products(products, ruling_data):
    """
    从产品列表和审批数据构建 results 列表。
    
    参数:
      products: list[dict], 从 Excel 读取的原始产品数据
      ruling_data: dict, key=code, value=审批结果
    """
    results = []
    for p in products:
        code = p.get('code', '')
        rd = ruling_data.get(code, {})

        result = {
            'brand': p.get('brand', ''),
            'code': code,
            'spec': p.get('spec', ''),
            'process': p.get('process', ''),
            'excel_sales': p.get('excel_sales', ''),
            'excel_inv': p.get('excel_inv', ''),
            'M': p.get('M', ''),
            'remark': p.get('remark', ''),
            's_cycle': rd.get('s_cycle', ''),
            'inventory': rd.get('inventory', ''),
            'gap': rd.get('gap', ''),
            'P': rd.get('P', ''),
            'verdict': rd.get('verdict', ''),
            'reason': rd.get('reason', ''),
            'trend': rd.get('trend', ''),
            'season_cap': rd.get('season_cap', ''),
            'is_subtotal': p.get('is_subtotal', False),
        }
        results.append(result)
    return results
