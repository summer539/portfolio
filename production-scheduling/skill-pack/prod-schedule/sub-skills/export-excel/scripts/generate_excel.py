#!/usr/bin/env python3
"""
某陶瓷企业智能排产 Excel 生成器 V2（索引版）
读取 schedule-a-a-result.json / schedule-a-b-result.json，
产出工艺分组、品牌系列分块的三Sheet排产Excel。

索引方式：素材总索引.json + 编号反查索引.json
分组层级：窑(规格) → 工艺 → 品牌系列 → 编号
"""

import json
import os
import io
from datetime import datetime
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from PIL import Image as PILImage

# ===================== 配置 =====================
MATERIALS_BASE = "skills/prod-schedule/assets/brand-materials"
_today = datetime.now()
SCHEDULE_DATE = f"{_today.year}年{_today.month}月{_today.day}日"
MONTH_SALES_LABEL = f"{_today.month}月1日-{_today.day}日销量(箱)"
if _today.month == 1:
    _prev_month = 12
else:
    _prev_month = _today.month - 1
PREV_MONTH_LABEL = f"{_prev_month}月销量(箱)"

# 规格→窑 映射
SPEC_TO_KILN = {
    "750×1500": "1窑715规格",
    "600×1200": "2窑612规格",
    "400×800":  "3窑4080规格",
    "800×800":  "5窑800规格",
}

# 样式常量
DARK_BLUE_FILL = PatternFill(start_color="002F54", end_color="002F54", fill_type="solid")
LIGHT_BLUE_FILL = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
MID_BLUE_FILL = PatternFill(start_color="B4C6E7", end_color="B4C6E7", fill_type="solid")
CRAFT_HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
RED_BG = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
WHITE_FONT = Font(name="微软雅黑", size=12, bold=True, color="FFFFFF")
BOLD_FONT = Font(name="微软雅黑", size=12, bold=True)
NORMAL_CN = Font(name="微软雅黑", size=12)
NUM_FONT = Font(name="Times New Roman", size=12)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin")
)
ROW_HEIGHT = 42

# 列定义 (1-indexed, 16列)
COL_MAP = {
    "brand": 1, "online_time": 2, "code": 3, "remark_col": 4,
    "plan_stock": 5, "real_stock": 6, "plan_qty": 7, "ai_qty": 8,
    "d7": 9, "d30": 10, "d90": 11,
    "bottom_label": 12, "thickness": 13, "carton_img": 14,
    "trend": 15, "ai_remark": 16
}
COL_WIDTHS = {1:10,2:8,3:20,4:12,5:10,6:10,7:10,8:10,9:10,10:10,11:10,
              12:22,13:12,14:18,15:10,16:30}
HEADERS = ["品牌","上线时间","生产编号","备注","计划库存(箱)","实时库存(箱)",
           "营销排产","AI排产","近7天日均销量","近30天日均销量","近90天日均销量",
           "底标","厚度","纸箱\n（图片）","趋势","AI备注"]

N_COLS = len(HEADERS)

# ===================== 素材索引加载 =====================
_material_index = None
_reverse_index = None
_material_by_series = None

def _load_indexes():
    global _material_index, _reverse_index, _material_by_series
    if _material_index is not None:
        return
    idx_path = os.path.join(MATERIALS_BASE, "素材总索引.json")
    rev_path = os.path.join(MATERIALS_BASE, "编号反查索引.json")
    with open(idx_path) as f:
        _material_index = json.load(f)
    with open(rev_path) as f:
        _reverse_index = json.load(f)
    _material_by_series = {}
    for entry in _material_index:
        key = (entry["窑规格"], entry["工艺"], entry["品牌系列"])
        _material_by_series[key] = entry


def get_material_for_code(code, spec_str):
    """根据产品编码+规格获取素材数据，返回 dict 或 None"""
    _load_indexes()
    kiln = SPEC_TO_KILN.get(spec_str, "")
    mapping = _reverse_index.get("编号映射", {})
    if code not in mapping:
        return None
    candidates = mapping[code]
    for c in candidates:
        if c["窑规格"] == kiln:
            key = (c["窑规格"], c["工艺"], c["品牌系列"])
            if key in _material_by_series:
                return dict(_material_by_series[key])
    if candidates:
        c0 = candidates[0]
        key = (c0["窑规格"], c0["工艺"], c0["品牌系列"])
        return dict(_material_by_series.get(key, {}))
    return None


# ===================== 图片处理 =====================
def create_centered_image(filepath, target_w, target_h, row, col, col_width_chars, num_rows, top_margin_px=0):
    pil = PILImage.open(filepath)
    pil_resized = pil.resize((target_w, target_h), PILImage.LANCZOS)
    buf = io.BytesIO()
    pil_resized.save(buf, format='PNG')
    buf.seek(0)
    img = XLImage(buf)
    total_w_px = col_width_chars * 7
    total_h_px = num_rows * ROW_HEIGHT * 1.333
    available_h_px = total_h_px - top_margin_px
    offset_x_emu = int(max(0, (total_w_px - target_w) / 2) * 9525)
    offset_y_emu = int((top_margin_px + max(0, (available_h_px - target_h) / 2)) * 9525)
    marker = AnchorMarker(col=col-1, colOff=offset_x_emu, row=row-1, rowOff=offset_y_emu)
    ext = XDRPositiveSize2D(cx=target_w * 9525, cy=target_h * 9525)
    img.anchor = OneCellAnchor(_from=marker, ext=ext)
    return img


# ===================== Sheet 行写入 =====================
def write_title_row(ws, row, kiln_label, spec_label, total_craft):
    """写入总标题行"""
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=N_COLS)
    cell = ws.cell(row=row, column=1,
                   value=f"{kiln_label} · {spec_label} · 智能排产计划 · {SCHEDULE_DATE}")
    cell.font = Font(name="微软雅黑", size=14, bold=True, color="FFFFFF")
    cell.fill = DARK_BLUE_FILL
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[row].height = 50
    return row + 1


def write_craft_header(ws, row, craft_name, series_count):
    """写入工艺分组标题行"""
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=N_COLS)
    cell = ws.cell(row=row, column=1, value=f"▌ {craft_name}（{series_count}个品牌系列）")
    cell.font = Font(name="微软雅黑", size=13, bold=True, color="FFFFFF")
    cell.fill = CRAFT_HEADER_FILL
    cell.alignment = LEFT
    cell.border = THIN_BORDER
    ws.row_dimensions[row].height = 38
    return row + 1


def write_header_row(ws, row):
    """写入16列表头"""
    for i, h in enumerate(HEADERS):
        cell = ws.cell(row=row, column=i+1, value=h)
        cell.font = WHITE_FONT
        cell.fill = DARK_BLUE_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(i+1)].width = COL_WIDTHS.get(i+1, 12)
    ws.row_dimensions[row].height = ROW_HEIGHT
    return row + 1


def write_product_row(ws, row, p, mat):
    """写入一条产品数据行"""
    brand = mat.get("品牌", p.get("brand", ""))
    code = p.get("code", "")
    remark = p.get("remark", "") or ""
    excel_stock = p.get("excel_stock", 0) or 0
    real_stock = p.get("inventory", 0) or 0
    plan_qty = p.get("plan_qty", 0) or 0
    ai_qty = p.get("ai_qty", 0) or 0
    d7 = p.get("d7", 0) or 0
    d30 = p.get("d30", 0) or 0
    d90 = p.get("d90", 0) or 0
    trend = p.get("trend", "") or ""
    ai_remark = p.get("ai_remark", "") or ""

    bottom_label = mat.get("底标", "")
    thickness = mat.get("厚度", "")
    if p.get("is_custom") and not bottom_label:
        bottom_label = "定制底标+"

    values = [brand, "", code, remark, excel_stock, real_stock,
              plan_qty, ai_qty, round(d7, 1), round(d30, 1), round(d90, 1),
              bottom_label, thickness, "", trend, ai_remark]

    for i, val in enumerate(values):
        cell = ws.cell(row=row, column=i+1, value=val if val != "" else None)
        cell.border = THIN_BORDER
        if i == 10 and val:
            cell.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
        else:
            cell.alignment = CENTER if i in [0,4,5,6,7,8,9] else LEFT
        if i in [4,5,6,7,8,9]:
            cell.font = NUM_FONT
            cell.number_format = '#,##0'
        if i in [6,7,8]:
            cell.number_format = '#,##0.0'
        if i not in [4,5,6,7,8,9]:
            cell.font = NORMAL_CN
        if i == 4 and isinstance(real_stock, (int, float)) and real_stock < 500:
            cell.fill = RED_BG
        if i == 13:
            if "上涨" in str(trend) or "🔥" in str(trend) or "激增" in str(trend):
                cell.font = Font(name="微软雅黑", size=12, color="FF0000", bold=True)
            elif "降温" in str(trend) or "骤降" in str(trend):
                cell.font = Font(name="微软雅黑", size=12, color="0000FF", bold=True)

    ws.row_dimensions[row].height = ROW_HEIGHT
    return row + 1


def write_sum_row(ws, row, series_label, products):
    """写入品牌系列合计行"""
    sum_plan_stock = sum(p.get("excel_stock", 0) or 0 for p in products)
    sum_real_stock = sum(p.get("inventory", 0) or 0 for p in products)
    sum_plan = sum(p.get("plan_qty", 0) or 0 for p in products)
    sum_ai = sum(p.get("ai_qty", 0) or 0 for p in products)

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    cell = ws.cell(row=row, column=1, value=f"{series_label} 合计：")
    cell.font = BOLD_FONT
    cell.alignment = LEFT
    cell.fill = LIGHT_BLUE_FILL
    cell.border = THIN_BORDER
    for c in range(2, 5):
        ws.cell(row=row, column=c).fill = LIGHT_BLUE_FILL
        ws.cell(row=row, column=c).border = THIN_BORDER
    sum_vals = [None, None, None, None, sum_plan_stock, sum_real_stock,
                sum_plan, sum_ai] + [None] * 8
    for i, val in enumerate(sum_vals):
        if i < 3: continue
        c = ws.cell(row=row, column=i+1, value=val)
        c.font = BOLD_FONT if val is not None else NORMAL_CN
        c.fill = LIGHT_BLUE_FILL
        c.border = THIN_BORDER
        c.alignment = CENTER
        if val is not None and isinstance(val, (int, float)):
            c.number_format = '#,##0'
    ws.row_dimensions[row].height = ROW_HEIGHT
    return row + 1


def write_side_spray_row(ws, row, mat):
    """写入侧喷行"""
    side_spray = mat.get("侧喷", "") if mat else ""
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=N_COLS)
    text = f"侧喷：{side_spray}" if side_spray else "侧喷：（素材待补充）"
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = NORMAL_CN
    cell.alignment = LEFT
    cell.border = THIN_BORDER
    ws.row_dimensions[row].height = ROW_HEIGHT
    return row + 1


def write_carton_row(ws, row, mat):
    """写入纸箱行"""
    carton_text = mat.get("纸箱名称", "") if mat else ""
    carton_mat = mat.get("纸箱", "") if mat else ""
    if carton_text:
        text = f"纸箱：{carton_mat}    纸箱名称：{carton_text}"
    elif carton_mat:
        text = f"纸箱：{carton_mat}"
    else:
        text = "纸箱：（素材待补充）"
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=N_COLS)
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = NORMAL_CN
    cell.alignment = LEFT
    cell.border = THIN_BORDER
    ws.row_dimensions[row].height = ROW_HEIGHT
    return row + 1


def write_footer(ws, row, all_products):
    """写入尾部：亮光总计 + 说明 + 制表人"""
    sum_plan_stock = sum(p.get("excel_stock", 0) or 0 for p in all_products)
    sum_real_stock = sum(p.get("inventory", 0) or 0 for p in all_products)
    sum_plan = sum(p.get("plan_qty", 0) or 0 for p in all_products)
    sum_ai = sum(p.get("ai_qty", 0) or 0 for p in all_products)
    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    cell = ws.cell(row=row, column=1, value="总计：")
    cell.font = BOLD_FONT
    cell.fill = MID_BLUE_FILL
    cell.alignment = LEFT
    cell.border = THIN_BORDER
    for c in range(2, 5):
        ws.cell(row=row, column=c).fill = MID_BLUE_FILL
        ws.cell(row=row, column=c).border = THIN_BORDER
    total_vals = [None, None, None, None, sum_plan_stock, sum_real_stock,
                  sum_plan, sum_ai] + [None] * 8
    for i, val in enumerate(total_vals):
        if i < 3: continue
        c = ws.cell(row=row, column=i+1, value=val)
        c.font = BOLD_FONT if val is not None else NORMAL_CN
        c.fill = MID_BLUE_FILL
        c.border = THIN_BORDER
        c.alignment = CENTER
        if val is not None and isinstance(val, (int, float)):
            c.number_format = '#,##0'
    ws.row_dimensions[row].height = ROW_HEIGHT
    row += 2
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=N_COLS)
    cell = ws.cell(row=row, column=1, value="说明：库存纸箱先用完，排产顺序按标注序号上线。定制产品需确认底标版本后再上线。")
    cell.font = NORMAL_CN
    cell.alignment = LEFT
    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=N_COLS)
    cell = ws.cell(row=row, column=1, value=f"制表人：AI智能排产助手                                    日期：{SCHEDULE_DATE}")
    cell.font = NORMAL_CN
    cell.alignment = LEFT
    return row


# ===================== 图片嵌入 =====================
def embed_series_images(ws, mat, series_start_row, series_end_row):
    """嵌入品牌系列的底标和纸箱图片"""
    if not mat:
        return
    col_bottom = COL_MAP["bottom_label"]
    col_carton = COL_MAP["carton_img"]
    num_merge_rows = series_end_row - series_start_row + 1
    if series_start_row < series_end_row:
        ws.merge_cells(start_row=series_start_row, start_column=col_bottom,
                       end_row=series_end_row, end_column=col_bottom)
        ws.merge_cells(start_row=series_start_row, start_column=col_carton,
                       end_row=series_end_row, end_column=col_carton)

    # 底标图片
    bottom_imgs = mat.get("底标图片", [])
    bottom_text = mat.get("底标", "")
    if bottom_imgs:
        img_rel = bottom_imgs[0]
        img_path = os.path.join(MATERIALS_BASE, img_rel)
        if os.path.exists(img_path):
            try:
                top_margin = 60 if bottom_text else 0
                img = create_centered_image(img_path, 120, 85,
                    series_start_row, col_bottom,
                    COL_WIDTHS[col_bottom], num_merge_rows, top_margin)
                ws.add_image(img)
                if bottom_text:
                    ws.cell(row=series_start_row, column=col_bottom).alignment = \
                        Alignment(horizontal="center", vertical="top", wrap_text=True)
            except Exception:
                pass

    # 纸箱图片
    carton_imgs = mat.get("纸箱图片", [])
    if carton_imgs:
        img_rel = carton_imgs[0]
        img_path = os.path.join(MATERIALS_BASE, img_rel)
        if os.path.exists(img_path):
            try:
                img = create_centered_image(img_path, 120, 85,
                    series_start_row, col_carton,
                    COL_WIDTHS[col_carton], num_merge_rows)
                ws.add_image(img)
            except Exception:
                pass


# ===================== Sheet 生成 =====================
def generate_sheet(ws, results, base_filter, kiln_label, spec_label):
    """生成一个基地的排产Sheet（工艺→品牌系列 分组）"""
    if results.get("empty") or "products" not in results:
        return
    products = results.get("products", [])
    if not products:
        return

    # 按 工艺→品牌系列 分组
    craft_series = {}  # {craft: {series_key: {mat, products}}}
    unmatched = []

    for p in products:
        code = p.get("code", "")
        mat = get_material_for_code(code, spec_label)
        if mat:
            craft = mat["工艺"]
            series = mat["品牌系列"]
            key = f"{craft}|{series}"
            if craft not in craft_series:
                craft_series[craft] = {}
            if key not in craft_series[craft]:
                craft_series[craft][key] = {"mat": mat, "products": []}
            craft_series[craft][key]["products"].append(p)
        else:
            unmatched.append(p)

    # 工艺排序：亮光→柔光→速洁釉→通体→仿古→高透
    craft_order = ["亮光", "柔光", "速洁釉", "通体", "仿古", "高透"]

    row = 1
    row = write_title_row(ws, row, kiln_label, spec_label, sum(len(v) for v in craft_series.values()))
    row += 1
    row = write_header_row(ws, row)

    all_rendered = []

    for craft in craft_order:
        if craft not in craft_series:
            continue
        series_dict = craft_series[craft]
        series_count = len(series_dict)

        # 工艺标题行
        row = write_craft_header(ws, row, craft, series_count)
        row += 1  # 空行

        for key, group in series_dict.items():
            mat = group["mat"]
            gp_products = group["products"]
            series_label = mat["品牌系列"]
            all_rendered.extend(gp_products)

            series_start_row = row

            # 产品数据行
            for idx, p in enumerate(gp_products):
                row = write_product_row(ws, row, p, mat)

            series_end_row = row - 1

            # 合计行
            row = write_sum_row(ws, row, series_label, gp_products)

            # 侧喷
            row = write_side_spray_row(ws, row, mat)

            # 纸箱
            row = write_carton_row(ws, row, mat)

            # 合并品牌系列区块
            if series_end_row > series_start_row:
                ws.merge_cells(start_row=series_start_row, start_column=1,
                               end_row=series_end_row, end_column=1)
                ws.merge_cells(start_row=series_start_row, start_column=2,
                               end_row=series_end_row, end_column=2)

            # 嵌入图片
            embed_series_images(ws, mat, series_start_row, series_end_row)

            row += 1  # 系列间空行

    # 未匹配产品（无素材）——放在末尾
    if unmatched:
        row = write_craft_header(ws, row, "未分类（无素材）", 1)
        row += 1
        no_mat = {"品牌": "?", "底标": "", "厚度": "", "侧喷": "（素材待补充）", "纸箱名称": "", "纸箱": ""}
        series_start_row = row
        for p in unmatched:
            row = write_product_row(ws, row, p, no_mat)
            all_rendered.append(p)
        series_end_row = row - 1
        row = write_sum_row(ws, row, "未分类", unmatched)
        row = write_side_spray_row(ws, row, no_mat)
        row = write_carton_row(ws, row, no_mat)
        if series_end_row > series_start_row:
            ws.merge_cells(start_row=series_start_row, start_column=1,
                           end_row=series_end_row, end_column=1)

    # 尾部
    write_footer(ws, row, all_rendered)
    ws.freeze_panes = "A4"


# ===================== Sheet3 汇总总览 =====================
def generate_summary_sheet(ws, a_data, b_data):
    """生成Sheet3：双基地21列汇总总览"""
    s_headers = ["序号","基地","品牌","编号","规格","工艺",PREV_MONTH_LABEL,MONTH_SALES_LABEL,
                 "近90天日均销量","近30天日均销量","近7天日均销量",
                 "计划库存(箱)","实时库存(箱)","营销建议","人工排产","AI建议",
                 "趋势","风险","优先级","vs营销","AI备注"]
    s_widths = [5,8,10,22,8,6,9,9,9,9,9,10,10,9,9,9,10,10,8,10,30]
    n_cols = len(s_headers)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    cell = ws.cell(row=1, column=1,
                   value=f"某陶瓷企业+B 基地 · 双基地排产汇总总览 · {SCHEDULE_DATE}")
    cell.font = Font(name="微软雅黑", size=14, bold=True, color="FFFFFF")
    cell.fill = DARK_BLUE_FILL
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 50

    row = 3
    for i, h in enumerate(s_headers):
        cell = ws.cell(row=row, column=i+1, value=h)
        cell.font = WHITE_FONT
        cell.fill = DARK_BLUE_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(i+1)].width = s_widths[i]
    ws.row_dimensions[row].height = ROW_HEIGHT
    row += 1

    seq = 0

    def write_section(ws, row, products, base_label):
        nonlocal seq
        products_sorted = sorted(products, key=lambda p: (p.get("priority", 0) or 0), reverse=True)
        brand_groups = {}
        for p in products_sorted:
            b = p["brand"]
            if b not in brand_groups:
                brand_groups[b] = []
            brand_groups[b].append(p)
        for brand, brand_products in brand_groups.items():
            for p in brand_products:
                seq += 1
                plan_qty = p.get("plan_qty", 0) or 0
                ai_qty = p.get("ai_qty", 0) or 0
                real_stock = p.get("inventory", 0) or 0
                d7 = p.get("d7", 0) or 0
                d30 = p.get("d30", 0) or 0
                d90 = p.get("d90", 0) or 0
                excel_stock = p.get("excel_stock", 0) or 0
                trend = p.get("trend", "") or ""
                risk = p.get("risk", "") or ""
                priority = p.get("priority", 0) or 0
                ai_remark = p.get("ai_remark", "") or ""
                vs_mkt = round((ai_qty - plan_qty) / plan_qty * 100, 1) if plan_qty > 0 else None
                vals = [seq, base_label, brand, p["code"], SPEC,
                        p.get("craft", ""), "", "",
                        round(d90,1), round(d30,1), round(d7,1),
                        excel_stock, real_stock,
                        plan_qty, "", ai_qty,
                        trend, risk, round(priority, 2),
                        f"{vs_mkt:+.1f}%" if vs_mkt is not None else "N/A",
                        ai_remark]
                for i, val in enumerate(vals):
                    cell = ws.cell(row=row, column=i+1, value=val if val != "" else None)
                    cell.border = THIN_BORDER
                    cell.font = NORMAL_CN if i not in [6,7,8,9,10,11,12,13,14,15,18] else NUM_FONT
                    cell.alignment = CENTER if i not in [3,20] else LEFT
                    if i == 12 and isinstance(real_stock, (int, float)) and real_stock < 500:
                        cell.fill = RED_BG
                    if i == 19 and vs_mkt is not None:
                        pct_abs = abs(vs_mkt)
                        color = "92D050" if pct_abs < 10 else ("FFD966" if pct_abs <= 50 else "FF6B6B")
                        cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
                ws.row_dimensions[row].height = ROW_HEIGHT
                row += 1

            b_plan = sum(p.get("plan_qty",0) or 0 for p in brand_products)
            b_ai = sum(p.get("ai_qty",0) or 0 for p in brand_products)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
            cell = ws.cell(row=row, column=1, value=f"{brand} 小计：营销{b_plan}箱 / AI{b_ai}箱")
            cell.font = BOLD_FONT
            cell.fill = LIGHT_BLUE_FILL
            cell.alignment = LEFT
            cell.border = THIN_BORDER
            for c in range(2, n_cols+1):
                ws.cell(row=row, column=c).fill = LIGHT_BLUE_FILL
                ws.cell(row=row, column=c).border = THIN_BORDER
            ws.row_dimensions[row].height = ROW_HEIGHT
            row += 1

        b_total_plan = sum(p.get("plan_qty",0) or 0 for p in products)
        b_total_ai = sum(p.get("ai_qty",0) or 0 for p in products)
        capacity_pct = a_data.get("capacity_pct", 0) if base_label == "某陶瓷企业" else b_data.get("capacity_pct", 0)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        cell = ws.cell(row=row, column=1,
                       value=f"{base_label}小计：营销{b_total_plan}箱 / AI{b_total_ai}箱 | 产能利用率{capacity_pct}")
        cell.font = BOLD_FONT
        cell.fill = MID_BLUE_FILL
        cell.alignment = LEFT
        cell.border = THIN_BORDER
        for c in range(2, n_cols+1):
            ws.cell(row=row, column=c).fill = MID_BLUE_FILL
            ws.cell(row=row, column=c).border = THIN_BORDER
        ws.row_dimensions[row].height = ROW_HEIGHT
        row += 2
        return row

    a_products = a_data.get("products", [])
    row = write_section(ws, row, a_products, "某陶瓷企业")
    b_products = b_data.get("products", [])
    if b_products:
        row = write_section(ws, row, b_products, "B 基地")

    total_plan = sum(p.get("plan_qty",0) or 0 for p in a_products + b_products)
    total_ai = sum(p.get("ai_qty",0) or 0 for p in a_products + b_products)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = ws.cell(row=row, column=1,
                   value=f"═══ 总计（某陶瓷企业+B 基地）：营销{total_plan}箱 / AI{total_ai}箱 ═══")
    cell.font = Font(name="微软雅黑", size=12, bold=True, color="FFFFFF")
    cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    cell.alignment = LEFT
    cell.border = THIN_BORDER
    for c in range(2, n_cols+1):
        ws.cell(row=row, column=c).fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        ws.cell(row=row, column=c).border = THIN_BORDER
    ws.row_dimensions[row].height = ROW_HEIGHT
    ws.freeze_panes = "A4"


# ===================== 主流程 =====================
SPEC = None

def main():
    global SPEC
    with open('/tmp/schedule-a-result.json') as f:
        a = json.load(f)
    with open('/tmp/schedule-b-result.json') as f:
        b = json.load(f)

    SPEC = a.get("spec", "600×1200")

    wb = Workbook()

    # Sheet 1: 某陶瓷企业
    ws1 = wb.active
    ws1.title = "某陶瓷企业·排产计划"
    daily_cap_a = a.get("daily_cap", 0)
    kiln_name = a.get("kiln", "2号窑")
    kiln_label = f"{kiln_name}（日产{daily_cap_a}箱）"
    generate_sheet(ws1, a, "某陶瓷企业", kiln_label, SPEC)

    # Sheet 2: B 基地
    ws2 = wb.create_sheet("B 基地·排产计划")
    daily_cap_jl = b.get("daily_cap", 0)
    kiln_name_jl = b.get("kiln", "B 基地窑")
    kiln_label_jl = f"{kiln_name_jl}（日产{daily_cap_jl}箱）" if daily_cap_jl else ""
    generate_sheet(ws2, b, "B 基地", kiln_label_jl, SPEC)

    # Sheet 3: 汇总总览
    ws3 = wb.create_sheet("汇总总览")
    generate_summary_sheet(ws3, a, b)

    for sn in list(wb.sheetnames):
        if sn not in ["某陶瓷企业·排产计划", "B 基地·排产计划", "汇总总览"]:
            del wb[sn]

    outpath = f"产出文件/对标{_today.month}月{_today.day}日-{SPEC.replace('×','x')}-智能排产优化方案-{_today.strftime('%Y%m%d')}.xlsx"
    wb.save(outpath)
    print(f"✅ 已生成: {outpath}")
    print(f"   Sheet1 某陶瓷企业·排产计划: {len(a['products'])}产品")
    b_products = b.get("products", [])
    print(f"   Sheet2 B 基地·排产计划: {len(b_products)}产品{'（空-B 基地无此规格排产）' if not b_products else ''}")
    print(f"   Sheet3 汇总总览")

    wb2 = openpyxl.load_workbook(outpath)
    for sn in wb2.sheetnames:
        ws = wb2[sn]
        print(f"   {sn}: {ws.max_row}行 × {ws.max_column}列")
        if "排产计划" in sn:
            print(f"      标题行: {ws.cell(1,1).value}")
            print(f"      表头行: {' | '.join([str(ws.cell(3,c).value or '') for c in range(1,17)])}")

if __name__ == "__main__":
    main()
