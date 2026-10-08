#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企微经营晨报 v1.1（技能版 daily-report）
- 每日生成"📅 某陶瓷企业 · 经营晨报"并发送到企微对话
- 模板结构：标题/口径 → 🏭产销率 → 📊经营概况 → 📈TOP5 → 💰回款率(月累计) → ⚠预警
- 口径与邮件日报完全一致：等级=优等(100001)+优AA(100009) / 组织=某陶瓷企业(100080)+B 基地(100082)
  / 仓库=成品一仓(119400)+成品三仓(177653) / 排除=某销售中心+某陶瓷有限公司 / 赠品计数量不计金额
- 数据方案：一次查询近30天出库窗口（内存切分昨日/前日/近30天/月累计销售额）+ 收款查询 + 本地库存快照
- 用法：
    python3 daily_morning_report_wecom.py                  # 计算昨天并发送企微
    python3 daily_morning_report_wecom.py --preview --date 2026-08-13   # 只打印文本不发送
"""
import sys, os, csv, subprocess, argparse
from datetime import datetime, timedelta
from collections import defaultdict

# ── 技能路径（分享/迁移无需改，自动定位）──
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.config import (SNAPSHOT_DIR, WECOM_ACCOUNT, WECOM_TARGET,
                            RATE_HIGH, RATE_LOW, STOCKOUT_THRESHOLD, OVERSTOCK_QTY,
                            TOP_N, DAYS_30)
from scripts.query_kingdee import KingdeeQuery, AUXPROP_FILTER, FINISHED_WAREHOUSE_FILTER, INTERNAL_CUSTOMERS


def load_snapshot(date_str):
    """读取快照CSV，返回 {产品名: 库存箱数}（两仓合并）；文件不存在返回 None"""
    path = os.path.join(SNAPSHOT_DIR, f"{date_str}.csv")
    if not os.path.exists(path):
        return None
    stock = defaultdict(float)
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            stock[row["物料编码"]] += float(row["库存(箱)"] or 0)
    return stock


def query_outstock_window(kq, start, end):
    """
    查询出库窗口（口径过滤），按周分段避免API单次Limit=10000截断，返回合并后的原始行列表
    """
    from datetime import timedelta as _td
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    all_rows = []
    seg_start = s
    while seg_start <= e:
        seg_end = min(seg_start + _td(days=6), e)
        fstr = (f"FDate>='{seg_start.strftime('%Y-%m-%d')}' AND FDate<='{seg_end.strftime('%Y-%m-%d')}' "
                f"AND FStockOrgID IN (100080,100082) AND {AUXPROP_FILTER} "
                f"AND {FINISHED_WAREHOUSE_FILTER} AND FDOCUMENTSTATUS='C'")
        rows = kq._query("SAL_OUTSTOCK",
            "FMaterialId.FName,FDate,FCustomerID.FName,FRealQty,FAllAmount,FIsFree",
            fstr, 10000)
        if len(rows) >= 10000:
            print(f"⚠️ 分段 {seg_start:%Y-%m-%d}~{seg_end:%Y-%m-%d} 触及Limit=10000，结果可能不完整！", file=sys.stderr)
        all_rows.extend(rows)
        seg_start = seg_end + _td(days=1)
    return all_rows


def query_receipts(kq, date_start, date_end):
    """收款：按客户聚合金额（销售出库回款率口径，与邮件日报一致）
    - FRECTOTALAMOUNTFOR分录行金额，查询带FBillNo触发分录行返回，行级汇总=单据总额
    - 排除内部客户"""
    rows = kq._query("AR_RECEIVEBILL",
        "FBillNo,FDATE,FCONTACTUNIT.FName,FRECTOTALAMOUNTFOR",
        f"FDate>='{date_start}' AND FDate<='{date_end}'", 20000)
    by_cust = defaultdict(float)
    for r in rows:
        cust = r.get('FCONTACTUNIT.FName', '') or '未知'
        if cust in INTERNAL_CUSTOMERS:
            continue
        by_cust[cust] += float(r.get('FRECTOTALAMOUNTFOR', 0) or 0)
    return by_cust


def fmt_wan(v):
    """元 → 万元字符串（1位小数，千分位），如 2487663.68 → '248.8'"""
    return f"{v / 10000:,.1f}"


def rate_status(rate):
    if rate is None:
        return "无销量"
    if rate > RATE_HIGH:
        return "库存累积"
    if rate < RATE_LOW:
        return "消化库存"
    return "产销平衡"


def build_report(date_str):
    """生成企微晨报文本，返回 (text, 摘要信息dict)"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    prev_str = (d - timedelta(days=1)).strftime("%Y-%m-%d")
    d30_start = (d - timedelta(days=DAYS_30)).strftime("%Y-%m-%d")
    month_start = d.strftime("%Y-%m-01")
    month_label = d.strftime("%Y-%m")

    kq = KingdeeQuery()

    # ── 1) 近30天出库窗口（内存切分昨日/前日/近30天/月累计）──
    rows = query_outstock_window(kq, d30_start, date_str)
    print(f"  出库窗口 {d30_start}~{date_str} 共 {len(rows)} 行", file=sys.stderr)

    # 昨日：按产品聚合 qty/amt/free + 客户集合
    y_by_prod = defaultdict(lambda: {'qty': 0.0, 'amt': 0.0, 'free': 0.0})
    y_customers = set()
    y_total_qty = y_total_amt = y_total_free = 0.0
    # 前日：总量/金额（环比用）
    p_total_qty = p_total_amt = 0.0
    # 近30天：按产品聚合 qty（库存天数分母）
    m30_by_prod = defaultdict(float)
    m30_total_qty = 0.0
    # 月累计：按客户聚合销售额（回款率分母）
    month_sales_by_cust = defaultdict(float)

    for r in rows:
        if r.get('FCustomerID.FName') in INTERNAL_CUSTOMERS:
            continue
        fdate = (r.get('FDate') or '')[:10]
        name = r.get('FMaterialId.FName', '') or '未知'
        cust = r.get('FCustomerID.FName', '') or '未知'
        qty = float(r.get('FRealQty', 0) or 0)
        amt = float(r.get('FAllAmount', 0) or 0)
        is_free = bool(r.get('FIsFree'))

        m30_by_prod[name] += qty
        m30_total_qty += qty

        if fdate == date_str:
            y_by_prod[name]['qty'] += qty
            y_by_prod[name]['amt'] += amt
            if is_free:
                y_by_prod[name]['free'] += qty
                y_total_free += qty
            y_total_qty += qty
            y_total_amt += amt
            y_customers.add(cust)
        elif fdate == prev_str:
            p_total_qty += qty
            p_total_amt += amt

        if fdate >= month_start:
            month_sales_by_cust[cust] += amt

    # ── 2) 回款（月累计）──
    receipts = query_receipts(kq, month_start, date_str)
    total_receipt = sum(receipts.values())
    month_sales_amt = sum(month_sales_by_cust.values())
    rate_overall = (total_receipt / month_sales_amt * 100) if month_sales_amt else 0.0

    # ── 3) 库存快照（昨日末 = 统计日快照）──
    snap_curr = load_snapshot(date_str)
    snap_prev = load_snapshot(prev_str)
    snap_ok = snap_curr is not None and snap_prev is not None

    # ── 4) 产销率（快照反推产量）──
    total_prod = 0.0
    prod_status_txt = ""
    if snap_ok:
        for code, curr in snap_curr.items():
            prev = snap_prev.get(code, 0.0)
            out = y_by_prod.get(code, {}).get('qty', 0.0)
            p = curr - prev + out
            if p > 0:
                total_prod += p
    else:
        prod_status_txt = f"⚠️ 快照不足（需 {prev_str} 与 {date_str} 两日快照），产销率/库存预警暂缺"

    overall_rate = (total_prod / y_total_qty * 100) if y_total_qty else 0.0

    # ── 5) 环比前日 ──
    qty_chg = ((y_total_qty - p_total_qty) / p_total_qty * 100) if p_total_qty else 0.0
    amt_chg = ((y_total_amt - p_total_amt) / p_total_amt * 100) if p_total_amt else 0.0

    # ── 6) TOP N 畅销产品（按昨日出库量）──
    top_items = sorted(y_by_prod.items(), key=lambda x: -x[1]['qty'])[:TOP_N]
    top_lines = []
    emoji_nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, (code, v) in enumerate(top_items):
        stock = snap_curr.get(code, 0.0) if snap_curr else 0.0
        daily30 = m30_by_prod.get(code, 0.0) / DAYS_30
        days = (stock / daily30) if daily30 > 0 else 0.0
        if daily30 <= 0 and stock > 0:
            days_txt = "—"
        else:
            days_txt = f"{days:.1f}"
        flag = "🔴" if (days < 3 or stock < STOCKOUT_THRESHOLD) else "✅"
        top_lines.append(
            f"{emoji_nums[i]} {code} — {v['qty']:,.0f}箱 / {fmt_wan(v['amt'])}万 / 可撑{days_txt}天 {flag}")

    # ── 7) 预警 ──
    warn_out = []
    warn_over = []
    if snap_ok:
        # 断货：今日在销但库存<500箱（按昨日销量降序）
        for code, v in sorted(y_by_prod.items(), key=lambda x: -x[1]['qty']):
            if v['qty'] > 0 and snap_curr.get(code, 0.0) < STOCKOUT_THRESHOLD:
                warn_out.append((code, snap_curr.get(code, 0.0)))
        # 积压：库存≥3000箱 且 近30天零出库（按库存降序）
        for code, stock in sorted(snap_curr.items(), key=lambda x: -x[1]):
            if stock >= OVERSTOCK_QTY and m30_by_prod.get(code, 0.0) <= 0:
                warn_over.append((code, stock))

    out_txt = "、".join(f"{c}（库存{s:,.0f}箱）" for c, s in warn_out[:4])
    if len(warn_out) > 4:
        out_txt += f"…共{len(warn_out)}个"
    over_txt = "、".join(f"{c}（{s:,.0f}箱）" for c, s in warn_over[:2])
    over_total = sum(s for _, s in warn_over)
    over_note = f"等{len(warn_over)}个——≥{OVERSTOCK_QTY:,}箱且近30天零出库，合计{over_total:,.0f}箱，建议促销去化" if len(warn_over) > 2 else "——≥3,000箱且近30天零出库，建议促销去化"

    # ── 8) 组装文本 ──
    stock_total = sum(snap_curr.values()) if snap_curr else 0.0
    sku_count = len(snap_curr) if snap_curr else 0
    days_total = (stock_total / (m30_total_qty / DAYS_30)) if m30_total_qty else 0.0

    lines = []
    lines.append(f"📅 某陶瓷企业 · 经营晨报（{date_str}）")
    lines.append("")
    lines.append(f"数据来源：金蝶ERP 销售出库/即时库存/收款单 · 统计日：{d.strftime('%m-%d')} · 口径：优等+优AA / 某陶瓷企业+B 基地 / 成品一仓+三仓 / 排除内部单")
    lines.append("")
    lines.append(f"🏭 昨日产销率：{overall_rate:.1f}%｜{rate_status(overall_rate) if snap_ok else '快照不足'}")
    if snap_ok:
        lines.append(f"产量 {total_prod:,.0f}箱 / 销量 {y_total_qty:,.0f}箱")
    else:
        lines.append(f"销量 {y_total_qty:,.0f}箱（产量待快照补齐）")
    lines.append("")
    lines.append("📊 昨日经营概况")
    lines.append(f"▫ 昨日出库：{y_total_qty:,.0f}箱 / {fmt_wan(y_total_amt)}万元（赠品{y_total_free:,.0f}箱）")
    lines.append(f"▫ 环比前日：{qty_chg:+.1f}%（金额{amt_chg:+.1f}%）")
    lines.append(f"▫ 发货客户：{len(y_customers)}家")
    if snap_ok:
        lines.append(f"▫ 成品仓优等品库存：{stock_total/10000:.1f}万箱 / {sku_count:,}个SKU / 可撑{days_total:.0f}天")
    lines.append("")
    lines.append(f"📈 昨日 TOP{TOP_N} 畅销产品（库存天数=当前库存÷近30天日均出库）")
    lines.extend(top_lines)
    lines.append("")
    lines.append(f"💰 回款率（{month_label}月累计）：{rate_overall:.1f}%")
    lines.append(f"本月收款 {fmt_wan(total_receipt)}万 / 本月销售额 {fmt_wan(month_sales_amt)}万")
    lines.append("")
    lines.append("⚠ 预警")
    if snap_ok:
        if warn_out:
            lines.append(f"🔴 断货预警：{out_txt}——今日在销但成品仓库存不足{STOCKOUT_THRESHOLD}箱，建议优先排产补货")
        else:
            lines.append("🔴 断货预警：无")
        if warn_over:
            lines.append(f"🟠 积压预警：{over_txt}{over_note}")
        else:
            lines.append("🟠 积压预警：无")
    else:
        lines.append(f"🔴🟠 快照不足，预警暂缺（{prod_status_txt}）")

    text = "\n".join(lines)
    summary = {
        "date": date_str, "overall_rate": overall_rate, "rate_overall": rate_overall,
        "total_qty": y_total_qty, "total_amt": y_total_amt, "total_prod": total_prod,
        "total_receipt": total_receipt, "month_sales_amt": month_sales_amt,
        "customers": len(y_customers), "stock_total": stock_total, "sku_count": sku_count,
        "warn_out": len(warn_out), "warn_over": len(warn_over), "snap_ok": snap_ok,
    }
    return text, summary


def send_wecom(text):
    """通过 openclaw CLI 发送企微消息"""
    cmd = ["openclaw", "message", "send",
           "--channel", "wecom",
           "--account", WECOM_ACCOUNT,
           "--target", WECOM_TARGET,
           "--message", text,
           "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"企微发送失败 rc={proc.returncode}: {proc.stderr[-800:]}")
    return proc.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="预览模式：只生成文本不发送")
    ap.add_argument("--date", help="计算指定日期（默认昨天）")
    args = ap.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now() - timedelta(days=1)
    date_str = d.strftime("%Y-%m-%d")

    text, s = build_report(date_str)

    if args.preview:
        print("=" * 60)
        print(text)
        print("=" * 60)
        print(f"摘要: 产销率={s['overall_rate']:.1f}% 回款率={s['rate_overall']:.1f}% "
              f"出库={s['total_qty']:,.0f}箱/{s['total_amt']/10000:.1f}万 客户={s['customers']}家 "
              f"库存={s['stock_total']/10000:.1f}万箱/{s['sku_count']}SKU "
              f"断货={s['warn_out']}个 积压={s['warn_over']}个")
        return

    out = send_wecom(text)
    print(f"✅ 企微晨报已发送: {date_str} 产销率={s['overall_rate']:.1f}% 回款率={s['rate_overall']:.1f}% "
          f"出库={s['total_qty']:,.0f}箱")
    print(f"   发送结果: {out.strip()[-300:]}")


if __name__ == "__main__":
    main()
