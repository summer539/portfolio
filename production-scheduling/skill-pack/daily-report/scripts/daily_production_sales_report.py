#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日产销率 & 回款率日报 v2.3（技能版 daily-report）
- 默认计算"昨天"的数据，发送HTML邮件 + CSV附件
- 结构：① 产销率（核心指标，最前）→ ② 昨日经营概况 → ③ 回款率（月累计口径）
- 产销率（路径B·快照反推）：产量 ≈ 昨日末快照 − 前日末快照 + 昨日出库；产销率 = 昨日产量 ÷ 昨日销量
- 销量口径：等级=优等(100001)+优AA(100009) / 组织=某陶瓷企业(100080)+B 基地(100082)
  / 仓库=成品一仓(119400)+成品三仓(177653) / 排除=某销售中心+某陶瓷有限公司 / 赠品计入出库量不计金额
- 回款率（月累计口径，销售出库回款率·业务指标）：当月1日~昨日收款额(AR_RECEIVEBILL.FRECTOTALAMOUNTFOR分录行金额，含FDATE收款日期)
  ÷ 当月1日~昨日已审核销售额(SAL_OUTSTOCK.FAllAmount AND FDOCUMENTSTATUS='C')，排除内部客户
- 附件：① 产销率CSV（产品明细）② 回款流水CSV（收款日期/客户/金额，每笔一行）
- 快照缺失时自动降级：只发经营概况+回款率部分并说明
- 用法：
    python3 daily_production_sales_report.py                 # 计算昨天并发送邮件
    python3 daily_production_sales_report.py --preview --date 2026-08-13   # 只生成HTML不发送
"""
import sys, os, csv, json, smtplib, argparse
from datetime import datetime, timedelta
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formataddr

# ── 技能路径（分享/迁移无需改，自动定位）──
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.config import (MAIL_USER, MAIL_PWD, SMTP_HOST, SMTP_PORT, MAIL_FROM_NAME,
                            SNAPSHOT_DIR, OUTPUT_DIR, RATE_HIGH, RATE_LOW)
from scripts.query_kingdee import KingdeeQuery, AUXPROP_FILTER, FINISHED_WAREHOUSE_FILTER, INTERNAL_CUSTOMERS


def query_sales(kq, date):
    """昨日销售出库：按产品聚合数量+金额（日报口径，见文件头注释）"""
    rows = kq._query("SAL_OUTSTOCK",
        "FMaterialId.FName,FRealQty,FAllAmount,FCustomerID.FName,FIsFree",
        f"FDate='{date}' AND FStockOrgID IN (100080,100082) AND {AUXPROP_FILTER} AND {FINISHED_WAREHOUSE_FILTER} AND FDOCUMENTSTATUS='C'",
        20000)
    by_prod = defaultdict(lambda: {'qty': 0.0, 'amt': 0.0, 'free_qty': 0.0})
    total_qty = 0.0
    total_amt = 0.0
    total_free = 0.0
    for r in rows:
        if r.get('FCustomerID.FName') in INTERNAL_CUSTOMERS:
            continue
        name = r.get('FMaterialId.FName', '') or '未知'
        qty = float(r.get('FRealQty', 0) or 0)
        amt = float(r.get('FAllAmount', 0) or 0)
        by_prod[name]['qty'] += qty
        by_prod[name]['amt'] += amt
        total_qty += qty
        total_amt += amt
        if r.get('FIsFree'):
            by_prod[name]['free_qty'] += qty
            total_free += qty
    return by_prod, total_qty, total_amt, total_free


def query_receipts(kq, date_start, date_end):
    """收款：按客户聚合金额 + 带日期的收款流水（销售出库回款率口径）
    - 用 FRECTOTALAMOUNTFOR（分录行金额）：查询必须带 FBillNo 触发分录行返回，行级金额汇总=单据总额
    - 排除内部客户，与销量口径一致"""
    rows = kq._query("AR_RECEIVEBILL",
        "FBillNo,FDATE,FCONTACTUNIT.FName,FRECTOTALAMOUNTFOR",
        f"FDate>='{date_start}' AND FDate<='{date_end}'", 20000)
    by_cust = defaultdict(float)
    details = []
    for r in rows:
        cust = r.get('FCONTACTUNIT.FName', '') or '未知'
        if cust in INTERNAL_CUSTOMERS:
            continue
        amt = float(r.get('FRECTOTALAMOUNTFOR', 0) or 0)
        by_cust[cust] += amt
        details.append((str(r.get('FDATE', ''))[:10], cust, amt, r.get('FBillNo', '')))
    details.sort(key=lambda x: (x[0], x[1]))
    return by_cust, details


def query_sales_by_customer(kq, date_start, date_end):
    """销售额：按客户聚合（日期范围，日报口径）"""
    rows = kq._query("SAL_OUTSTOCK",
        "FCustomerID.FName,FAllAmount",
        f"FDate>='{date_start}' AND FDate<='{date_end}' AND FStockOrgID IN (100080,100082) AND {AUXPROP_FILTER} AND {FINISHED_WAREHOUSE_FILTER} AND FDOCUMENTSTATUS='C'",
        20000)
    by_cust = defaultdict(float)
    for r in rows:
        if r.get('FCustomerID.FName') in INTERNAL_CUSTOMERS:
            continue
        cust = r.get('FCustomerID.FName', '') or '未知'
        by_cust[cust] += float(r.get('FAllAmount', 0) or 0)
    return by_cust


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


def calc_production(snap_prev, snap_curr, sales_by_prod):
    """产量反推: 产量 = 昨日末 − 前日末 + 昨日出库（忽略杂项，口径标注）"""
    prod = {}
    for code, curr in snap_curr.items():
        prev = snap_prev.get(code, 0.0)
        out = sales_by_prod.get(code, {}).get('qty', 0.0)
        p = curr - prev + out
        if p > 0:
            prod[code] = p
    return prod


def rate_status(rate):
    """产销率状态标注"""
    if rate is None:
        return ("无销量", "#999999")
    if rate > RATE_HIGH:
        return ("库存累积", "#E6A23C")   # 黄：生产>销售
    if rate < RATE_LOW:
        return ("消化库存", "#67C23A")   # 绿：销售>生产
    return ("产销平衡", "#409EFF")       # 蓝：接近100%


def build_html(date_str, month_label, sales_by_prod, total_qty, total_amt, total_free,
               receipts, sales_by_cust, month_sales_amt, prod_rows, prod_status, overall_rate):
    """组装邮件HTML（v2.2 模板：产销率→经营概况→回款率[月累计口径]）"""
    total_receipt = sum(receipts.values())
    # 回款率 = 月累计收款 ÷ 月累计销售额（2026-08-13 用户确认按月口径）
    rate_overall = (total_receipt / month_sales_amt * 100) if month_sales_amt else 0

    # 客户合并（本月收款+本月销售额+回款率），按收款降序
    cust_merged = []
    for cust, recv in receipts.items():
        sal = sales_by_cust.get(cust, 0.0)
        cr = (recv / sal * 100) if sal else 0
        cust_merged.append((cust, recv, sal, cr))
    cust_merged.sort(key=lambda x: -x[1])

    # ── ① 产销率表格（核心，Top30，颜色标注状态）──
    top_rows = prod_rows[:30]
    def _row_html(c, p, s, r):
        st, color = rate_status(r)
        rate_cell = f"<b>{r:.1f}%</b>" if r is not None else "—"
        return (f"<tr><td>{c}</td><td style='text-align:right'>{p:,.0f}</td>"
                f"<td style='text-align:right'>{s:,.0f}</td>"
                f"<td style='text-align:right'>{rate_cell}</td>"
                f"<td style='color:{color}'>{st}</td></tr>")
    prod_html = "".join(_row_html(c, p, s, r) for c, p, s, r in top_rows)
    prod_table = ""
    if prod_rows:
        prod_table = (f"<table border=1 cellspacing=0 cellpadding=5>"
                      f"<tr><th>产品</th><th>产量(箱)</th><th>销量(箱)</th><th>产销率</th><th>状态</th></tr>"
                      f"{prod_html}</table>")
        if len(prod_rows) > 30:
            prod_table += f"<p style='color:#888'>（仅显示产量前30，完整见附件CSV，共{len(prod_rows)}个产品）</p>"

    # ── ② 昨日经营概况 ──
    overview = f"""
    <h3>📊 昨日经营概况</h3>
    <table border=1 cellspacing=0 cellpadding=5>
      <tr><td>出库总量</td><td><b>{total_qty:,.0f}</b> 箱（含赠品 {total_free:,.0f} 箱）</td></tr>
      <tr><td>销售总额</td><td><b>{total_amt:,.0f}</b> 元</td></tr>
      <tr><td>反推产量合计</td><td><b>{sum(p for _, p, _, _ in prod_rows):,.0f}</b> 箱（{len(prod_rows)} 个产品有产量）</td></tr>
      <tr><td>整体产销率</td><td><b style="font-size:16px">{overall_rate:.1f}%</b></td></tr>
      <tr><td>本月累计收款</td><td>{total_receipt:,.0f} 元（{len(receipts)} 个客户）</td></tr>
    </table>
    """

    # ── ③ 回款率（月累计口径）──
    receipt_html = ""
    if cust_merged:
        receipt_html = ("<table border=1 cellspacing=0 cellpadding=5>"
                        "<tr><th>客户</th><th>本月收款(元)</th><th>本月销售额(元)</th><th>回款率</th></tr>" +
                        "".join(
                            f"<tr><td>{c}</td><td style='text-align:right'>{r:,.0f}</td>"
                            f"<td style='text-align:right'>{s:,.0f}</td>"
                            f"<td style='text-align:right'>{cr:.0f}%</td></tr>"
                            for c, r, s, cr in cust_merged) + "</table>")

    html = f"""
    <html><body style="font-family:微软雅黑,sans-serif">
    <h2>📊 每日产销率 & 回款率日报 — {date_str}</h2>

    <h3>🏭 产销率（核心指标）</h3>
    <p style="color:#888">产量≈昨日末快照−前日末快照+昨日出库（忽略杂项出入库）；产销率=产量÷销量。<br>
    状态说明：<span style="color:#409EFF">■</span>产销平衡(90~110%)　<span style="color:#E6A23C">■</span>库存累积(&gt;110%)　<span style="color:#67C23A">■</span>消化库存(&lt;90%)</p>
    {prod_status if prod_status else ''}
    {prod_table}

    {overview}

    <h3>💰 回款率（{month_label}累计）</h3>
    <p>本月累计收款：<b>{total_receipt:,.0f} 元</b>（{len(receipts)} 个客户）<br>
       本月累计销售额：<b>{month_sales_amt:,.0f} 元</b><br>
       <b style="font-size:16px">整体回款率：{rate_overall:.1f}%</b></p>
    {receipt_html}

    <p style="color:#888">口径：等级=优等(100001)+优AA(100009)；组织=某陶瓷企业+B 基地；仓库=成品一仓+成品三仓；排除=某销售中心+某陶瓷有限公司；赠品计入出库量不计金额。<br>
    由智能排产助手自动生成</p>
    </body></html>
    """
    return html, rate_overall


def send_mail(subject, html, attachments):
    msg = MIMEMultipart()
    msg["From"] = formataddr((str(Header(MAIL_FROM_NAME, "utf-8")), MAIL_USER))
    msg["To"] = MAIL_USER
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(html, "html", "utf-8"))
    for fname, content in attachments:
        part = MIMEApplication(content)
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", fname))
        msg.attach(part)
    s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=60)
    s.login(MAIL_USER, MAIL_PWD)
    s.sendmail(MAIL_USER, [MAIL_USER], msg.as_string())
    s.quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="预览模式：生成HTML不发送")
    ap.add_argument("--date", help="计算指定日期（默认昨天）")
    args = ap.parse_args()

    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        d = datetime.now() - timedelta(days=1)
    date_str = d.strftime("%Y-%m-%d")
    kq = KingdeeQuery()

    # ── 数据准备 ──
    # 回款率按月累计口径：当月1日 ~ 目标日（2026-08-13 用户确认）
    month_start = d.strftime("%Y-%m-01")
    month_label = d.strftime("%Y-%m")
    sales_by_prod, total_qty, total_amt, total_free = query_sales(kq, date_str)
    receipts, receipt_details = query_receipts(kq, month_start, date_str)
    sales_by_cust = query_sales_by_customer(kq, month_start, date_str)
    month_sales_amt = sum(sales_by_cust.values())

    # ── ① 产销率（需前后两天快照）──
    snap_prev = load_snapshot((d - timedelta(days=1)).strftime("%Y-%m-%d"))
    snap_curr = load_snapshot(date_str)
    prod_status = ""
    prod_rows = []
    if snap_prev is None or snap_curr is None:
        prod_status = (f"⚠️ 快照不足：需要 {date_str} 和 {(d-timedelta(days=1)).strftime('%Y-%m-%d')} "
                       f"两日快照（当前有 {'有' if snap_curr else '无'}昨日、{'有' if snap_prev else '无'}前日）。"
                       f"快照自每日23:59由 daily_stock_snapshot.py 生成。")
    else:
        production = calc_production(snap_prev, snap_curr, sales_by_prod)
        for code, p in production.items():
            s = sales_by_prod.get(code, {}).get('qty', 0.0)
            rate = p / s * 100 if s > 0 else None  # 产销率 = 产量 ÷ 销量
            prod_rows.append((code, p, s, rate))
        prod_rows.sort(key=lambda x: -x[1])

    # 整体产销率 = Σ产量 ÷ Σ销量
    total_prod = sum(p for _, p, _, _ in prod_rows)
    overall_rate = (total_prod / total_qty * 100) if total_qty else 0

    html, rate_overall = build_html(date_str, month_label, sales_by_prod, total_qty, total_amt, total_free,
                                    receipts, sales_by_cust, month_sales_amt, prod_rows, prod_status, overall_rate)

    # 附件
    attachments = []
    if prod_rows:
        buf = "产品,产量(箱),销量(箱),产销率(%)\n" + "".join(
            f"{c},{p:.0f},{s:.0f},{r:.1f}\n" if r is not None else f"{c},{p:.0f},{s:.0f},无销量\n"
            for c, p, s, r in prod_rows)
        attachments.append((f"产销率-{date_str}.csv", buf.encode("utf-8-sig")))
    buf2 = "收款日期,客户,收款金额(元),单据号\n" + "".join(
        f"{dt},{c},{amt:.2f},{bn}\n" for dt, c, amt, bn in receipt_details)
    attachments.append((f"回款流水-{month_label}.csv", buf2.encode("utf-8-sig")))

    if args.preview:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out = os.path.join(OUTPUT_DIR, f"日报预览-{date_str}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ 预览已生成（未发送）: {out}")
        print(f"   整体产销率={overall_rate:.1f}% 整体回款率={rate_overall:.1f}% 出库={total_qty:,.0f}箱 销售额={total_amt:,.0f}元")
        return

    send_mail(f"【产销率&回款率日报】{date_str} 产销率{overall_rate:.0f}% 回款率{rate_overall:.0f}%", html, attachments)
    print(f"✅ 日报已发送: {date_str} 产销率={overall_rate:.1f}% 回款率={rate_overall:.1f}% 出库={total_qty:,.0f} 销售额={total_amt:,.0f}")
    if prod_status:
        print(f"ℹ️ 产销率: {prod_status}")


if __name__ == "__main__":
    main()
