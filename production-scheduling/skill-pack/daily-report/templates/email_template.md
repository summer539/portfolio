# 邮箱日报 HTML 模板（daily-report 技能）

> 发送渠道：SMTP 邮件（腾讯企业邮 SSL，配置见 `scripts/config.py`）
> 发送脚本：`scripts/daily_production_sales_report.py`
> 结构：① 产销率（核心，最前）→ ② 昨日经营概况 → ③ 回款率（月累计）
> 页面样式：微软雅黑；状态色：产销平衡=蓝#409EFF、库存累积=黄#E6A23C、消化库存=绿#67C23A

## 模板结构（HTML 骨架）

```html
<html><body style="font-family:微软雅黑,sans-serif">
<h2>📊 每日产销率 & 回款率日报 — {date_str}</h2>

<!-- ① 产销率（核心指标） -->
<h3>🏭 产销率（核心指标）</h3>
<p style="color:#888">产量≈昨日末快照−前日末快照+昨日出库（忽略杂项出入库）；产销率=产量÷销量。
状态说明：■产销平衡(90~110%)　■库存累积(>110%)　■消化库存(<90%)</p>
{快照缺失提示（如有）}
<table border=1 cellspacing=0 cellpadding=5>
  <tr><th>产品</th><th>产量(箱)</th><th>销量(箱)</th><th>产销率</th><th>状态</th></tr>
  {产量Top30行：产品 / 产量 / 销量 / 产销率% / 状态(带颜色)}
</table>
{>30个时附注：仅显示产量前30，完整见附件CSV，共N个产品}

<!-- ② 昨日经营概况 -->
<h3>📊 昨日经营概况</h3>
<table border=1 cellspacing=0 cellpadding=5>
  <tr><td>出库总量</td><td><b>{total_qty}</b> 箱（含赠品 {total_free} 箱）</td></tr>
  <tr><td>销售总额</td><td><b>{total_amt}</b> 元</td></tr>
  <tr><td>反推产量合计</td><td><b>{Σ产量}</b> 箱（{N} 个产品有产量）</td></tr>
  <tr><td>整体产销率</td><td><b>{overall_rate:.1f}%</b></td></tr>
  <tr><td>本月累计收款</td><td>{total_receipt} 元（{N} 个客户）</td></tr>
</table>

<!-- ③ 回款率（月累计口径） -->
<h3>💰 回款率（{YYYY-MM}累计）</h3>
<p>本月累计收款：<b>{total_receipt} 元</b>（{N} 个客户）<br>
   本月累计销售额：<b>{month_sales_amt} 元</b><br>
   <b style="font-size:16px">整体回款率：{rate_overall:.1f}%</b></p>
<table border=1 cellspacing=0 cellpadding=5>
  <tr><th>客户</th><th>本月收款(元)</th><th>本月销售额(元)</th><th>回款率</th></tr>
  {按客户合并表：收款降序}
</table>

<p style="color:#888">口径：等级=优等(100001)+优AA(100009)；组织=某陶瓷企业+B 基地；仓库=成品一仓+成品三仓；
排除=某销售中心+某陶瓷有限公司；赠品计入出库量不计金额。<br>
由智能排产助手自动生成</p>
</body></html>
```

## 各部分参数计算规则

| 区块 | 参数 | 计算规则 | 数据来源 |
|------|------|----------|----------|
| ① 产销率表 | 产量(箱) | 该产品：昨日末快照 − 前日末快照 + 昨日出库（结果>0才计入，忽略杂项出入库） | 快照CSV + SAL_OUTSTOCK |
| ① 产销率表 | 销量(箱) | 该产品昨日出库量（日报口径） | SAL_OUTSTOCK |
| ① 产销率表 | 产销率 | 产量÷销量×100；无销量显示"—"；状态阈值：<90%消化库存(绿)、90~110%产销平衡(蓝)、>110%库存累积(黄) | 计算 |
| ② 经营概况 | 出库总量/销售总额 | 昨日 FRealQty / FAllAmount 合计（赠品行计入数量不计金额） | SAL_OUTSTOCK |
| ② 经营概况 | 反推产量合计 | Σ各产品产量（同①） | 计算 |
| ② 经营概况 | 整体产销率 | Σ产量 ÷ Σ销量 ×100 | 计算 |
| ② 经营概况 | 本月累计收款 | 当月1日~统计日 AR_RECEIVEBILL.FRECAMOUNTFOR 合计（排除内部客户） | AR_RECEIVEBILL |
| ③ 回款率 | 本月累计收款 | 当月1日~统计日 AR_RECEIVEBILL.FRECTOTALAMOUNTFOR（分录行金额，带FBillNo查询）合计，排除内部客户 | AR_RECEIVEBILL |
| ③ 回款率 | 本月累计销售额 | 当月1日~统计日 SAL_OUTSTOCK.FAllAmount 合计（日报口径 + FDOCUMENTSTATUS='C' 已审核） | SAL_OUTSTOCK |
| ③ 回款率 | 客户回款率 | 该客户本月收款 ÷ 该客户本月销售额 ×100（无销售额显示空） | 计算 |

## 附件清单（随邮件发送）

| 附件 | 内容 | 说明 |
|------|------|------|
| `产销率-{date}.csv` | 产品,产量(箱),销量(箱),产销率(%) | 全部产品（不限于Top30），无销量标"无销量" |
| `回款流水-{month}.csv` | 收款日期,客户,收款金额(元),单据号 | 每笔收款分录一行（含FDATE/FBillNo），按日期排序，排除内部客户 |

## 邮件头

- 收件人/发件人：`config.py` 的 MAIL_USER（自收自发）
- 主题：`【产销率&回款率日报】{date} 产销率{N}% 回款率{N}%`
- 发件人显示名：`MAIL_FROM_NAME`
