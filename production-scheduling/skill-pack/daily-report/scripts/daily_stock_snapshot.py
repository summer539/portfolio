#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日库存快照 v1.1（技能版 daily-report）
- 拉取 某陶瓷企业成品一仓(119400) + B 基地成品三仓(177653) 全量库存（仅优等品：优等100001 + 优AA 100009）
- 按物料FName聚合，保存CSV快照到 data/snapshots/
- 发送摘要邮件 + CSV附件
- 用途：积累每日库存快照，用于反推日产量/产销率/库存天数
- 注意：不跳过0数量行！库存为0的产品也要记录，否则产销率反推会漏算
- 用法：python3 daily_stock_snapshot.py
"""
import sys, os, csv, smtplib, json
from datetime import datetime
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formataddr

# ── 技能路径（分享/迁移无需改，自动定位）──
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.config import (MAIL_USER, MAIL_PWD, SMTP_HOST, SMTP_PORT,
                            SNAPSHOT_DIR, STOCKOUT_THRESHOLD, OVERSTOCK_QTY)
from scripts.query_kingdee import KingdeeQuery, WAREHOUSES, AUXPROP_FILTER

# 阈值（与 config.py 保持一致，告急/积压判定）
LOW_STOCK_THRESHOLD = STOCKOUT_THRESHOLD    # 库存告急阈值（箱）
OVERSTOCK_THRESHOLD = OVERSTOCK_QTY         # 库存积压阈值（箱）


def fetch_warehouse(kq, wh_id):
    """拉取单个仓库全量库存（仅优等品+优AA），返回 [{name, number, spec, qty}]"""
    r = kq.api.BillQuery({
        'FormId': 'STK_Inventory',
        'FieldKeys': 'FMaterialId.FSpecification,FBaseQty,FMaterialId.FName,FMaterialId.FNumber',
        'FilterString': f"FStockId={wh_id} AND {AUXPROP_FILTER}",
        'Limit': 8000,
    })
    data = json.loads(r) if isinstance(r, str) else r
    products = defaultdict(lambda: {'name': '', 'number': '', 'spec': '', 'qty': 0.0})
    for item in data:
        name = item.get('FMaterialId.FName', '') or ''
        spec = item.get('FMaterialId.FSpecification', '') or ''
        number = item.get('FMaterialId.FNumber', '') or ''
        qty = float(item.get('FBaseQty', 0) or 0)
        # 注意：不跳过0数量行！库存为0的产品也要记录，否则产销率反推会漏算
        key = name or number
        products[key]['name'] = name
        products[key]['number'] = number
        products[key]['spec'] = spec
        products[key]['qty'] += qty
    return list(products.values())


def send_mail(subject, html_body, attachments):
    """发送邮件（SMTP SSL）"""
    msg = MIMEMultipart()
    msg["From"] = formataddr((str(Header("库存快照机器人", "utf-8")), MAIL_USER))
    msg["To"] = MAIL_USER
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    for fname, content in attachments:
        part = MIMEApplication(content)
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", fname))
        msg.attach(part)
    s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=60)
    s.login(MAIL_USER, MAIL_PWD)
    s.sendmail(MAIL_USER, [MAIL_USER], msg.as_string())
    s.quit()


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    kq = KingdeeQuery()

    all_rows = []          # CSV行
    summary = []           # 邮件摘要
    grand_total = 0
    grand_count = 0
    spec_totals = defaultdict(lambda: {'count': 0, 'qty': 0.0})
    low_stock, overstock = [], []

    for wh_name, wh in WAREHOUSES.items():
        items = fetch_warehouse(kq, wh["id"])
        wh_total = sum(i['qty'] for i in items)
        grand_total += wh_total
        grand_count += len(items)
        summary.append(f"<b>{wh_name} {wh['id']}</b>：{len(items)} 个产品 / {wh_total:,.0f} 箱")
        for i in items:
            all_rows.append([today, wh_name, i['name'], i['number'], i['spec'], round(i['qty'], 2)])
            spec_totals[i['spec'] or '未标注']['count'] += 1
            spec_totals[i['spec'] or '未标注']['qty'] += i['qty']
            if i['qty'] < LOW_STOCK_THRESHOLD:
                low_stock.append((wh_name, i['name'], i['qty']))
            if i['qty'] >= OVERSTOCK_THRESHOLD:
                overstock.append((wh_name, i['name'], i['qty']))

    # ── CSV 快照 ──
    csv_path = os.path.join(SNAPSHOT_DIR, f"{today}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["日期", "仓库", "物料编码", "系统编码", "规格", "库存(箱)"])
        w.writerows(all_rows)

    # 同时追加到累计快照（all_snapshots.csv），方便趋势分析
    acc_path = os.path.join(SNAPSHOT_DIR, "all_snapshots.csv")
    is_new = not os.path.exists(acc_path)
    with open(acc_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["日期", "仓库", "物料编码", "系统编码", "规格", "库存(箱)"])
        w.writerows(all_rows)

    # ── 邮件正文 ──
    spec_html = "".join(
        f"<tr><td>{s}</td><td>{v['count']}</td><td style='text-align:right'>{v['qty']:,.0f}</td></tr>"
        for s, v in sorted(spec_totals.items(), key=lambda x: -x[1]['qty']))
    low_html = "".join(f"<tr><td>{w}</td><td>{n}</td><td style='text-align:right'>{q:,.0f}</td></tr>"
                       for w, n, q in sorted(low_stock, key=lambda x: x[2])) or "<tr><td colspan=3>无</td></tr>"
    over_html = "".join(f"<tr><td>{w}</td><td>{n}</td><td style='text-align:right'>{q:,.0f}</td></tr>"
                        for w, n, q in sorted(overstock, key=lambda x: -x[2])) or "<tr><td colspan=3>无</td></tr>"

    html = f"""
    <html><body style="font-family:微软雅黑,sans-serif">
    <h2>📦 每日库存快照 {today}</h2>
    <p><b>合计：{grand_count} 个产品 / {grand_total:,.0f} 箱</b></p>
    <p>{'<br>'.join(summary)}</p>
    <h3>按规格分布</h3>
    <table border=1 cellspacing=0 cellpadding=5>
      <tr><th>规格</th><th>产品数</th><th>库存(箱)</th></tr>{spec_html}
    </table>
    <h3>🚨 库存告急（&lt;{LOW_STOCK_THRESHOLD}箱，全部 {len(low_stock)} 个）</h3>
    <table border=1 cellspacing=0 cellpadding=5>
      <tr><th>仓库</th><th>编码</th><th>库存(箱)</th></tr>{low_html}
    </table>
    <h3>⛔ 库存积压（≥{OVERSTOCK_THRESHOLD}箱，全部 {len(overstock)} 个）</h3>
    <table border=1 cellspacing=0 cellpadding=5>
      <tr><th>仓库</th><th>编码</th><th>库存(箱)</th></tr>{over_html}
    </table>
    <p style="color:#888">快照文件：{csv_path}<br>由智能排产助手自动生成</p>
    </body></html>
    """

    with open(csv_path, "rb") as f:
        csv_content = f.read()
    send_mail(f"【库存快照】{today} 某陶瓷企业+B 基地成品仓 {grand_total:,.0f}箱",
              html, [(f"库存快照-{today}.csv", csv_content)])

    print(f"✅ 快照完成: {grand_count}产品/{grand_total:,.0f}箱 → {csv_path}")
    print(f"✅ 邮件已发送至 {MAIL_USER}")


if __name__ == "__main__":
    main()
