---
name: schedule-b
description: B 基地智能排产子技能。读取data-fetch产出的产品数据JSON，过滤JL产品（仅400×800），执行规则校核+V6多时间维度缺口裁决，产出B 基地排产结果JSON。父技能：prod-schedule。
---

# B 基地排产

**父技能：** prod-schedule（路由器并行调用）
**输入：** `/tmp/schedule-data.json`
**输出：** `/tmp/schedule-b-result.json`

## 适用范围

- **仅 400×800 规格**（B 基地窑，日产70000方/31250箱）
- 仅处理 `b%` 编码前缀的产品
- 其他规格（600×1200/750×1500/800×800）无B 基地产品，直接跳过

## 窑炉参数

| 规格 | 窑号 | 日产能(方) | FVolume(㎡/箱) | 日产能(箱) |
|------|------|:---:|:---:|:---:|
| 400×800 | B 基地窑 | 70,000 | 2.24 | 31,250 |

> ⚠️ B 基地仅有一条窑（B 基地窑·400×800），无其他规格。

## 操作步骤

### 1. 读取数据并过滤
```python
import json
with open('/tmp/schedule-data.json', 'r') as f:
    data = json.load(f)

# 优先按base字段，缺失时回退到编码前缀JL%
b_products = [p for p in data['products'] if p.get('base') == 'B 基地']
if not b_products:
    # 容错回退：base字段可能未设置（data-fetch可能漏设）
    b_products = [p for p in data['products'] if not p.get('base') and p['code'].startswith('b')]
    if b_products:
        print("⚠️ base字段缺失，回退到编码前缀JL%判定")

if not b_products:
    print("ℹ️ B 基地无此规格排产需求，跳过")
    # 🔴 必须写空结果文件，不能静默退出
    with open('/tmp/schedule-b-result.json', 'w') as f:
        json.dump({"base": "B 基地", "empty": True, "spec": data['meta']['spec']}, f, ensure_ascii=False)
    return
```

### 2. 规则校核

#### 2.1 最低起排量校验
- 所有产品（含定制）≥1500箱
- 新品≥3000箱

#### 2.2 淡季策略（6/7/8月）
- 标记销量占比<5%的产品，提示可暂缓（仅供参考，不限产能）

#### 2.3 焕白(-HB)产品处理
- 使用 data-fetch 已合并的总库存
- 切换节点（仅参考）：400×800→6月28日
- -HB产品库存已在 data-fetch 阶段合并

### 2.5 产能预评估
- 总排产 vs 7天产能上限（31250箱×7=218750箱）

### 3. V6 多时间维度耦合缺口裁决

与某陶瓷企业排产完全相同的算法（参考 schedule-a/SKILL.md 第3节），差异仅在窑炉参数：

- 日产能(箱) = 31250（B 基地窑）
- 产能上限：P ≤ 31250（满产）
- 批次取整：`P = round(P / 500) × 500`

**三日均/趋势判定/双缺口/趋势加成/安全阀/裁决/营销参照/风险标记/优先级** — 算法与 schedule-a 完全一致，直接复用。

### 4. 必须展示 Top3 完整计算链路

（同 schedule-a，从B 基地产品中选优先级最高的3个）

### 5. 输出 — 打印并写JSON

**必须打印：**
- 基地+窑号确认、B 基地窑参数
- 违规统计
- Top3计算链路
- 最终统计：营销X箱 → AI Y箱（±Z%），产能利用率P%

**写入 `/tmp/schedule-b-result.json`**

## 输出契约

```json
{
  "base": "B 基地",
  "kiln": "B 基地窑",
  "spec": "400*800",
  "daily_cap": 31250,
  "total_marketing": 45000,
  "total_ai": 42000,
  "capacity_pct": 0.19,
  "violations": [...],
  "anomalies": {
    "stock_critical": [...],
    "overstock": [...],
    "surge": 0,
    "plunge": 0
  },
  "top3_calc": [...],
  "products": [
    {
      "brand": "...",
      "code": "SDA4M02",
      "spec": "400*800",
      "ai_qty": 3000,
      "plan_qty": 3000,
      "ruling": "✅ 批准",
      "trend": "➡️平稳",
      "risk": null,
      "priority": 0.65,
      "d7": 50, "d30": 50, "d90": 50,
      "inventory": 2000, "inventory_days": 40,
      "calc_chain": "...",
      "ai_remark": "库存充足，近30天日均出库50箱，趋势平稳，库存健康无需紧急排产"
    }
  ]
}
```

空结果（非400×800规格）：
```json
{"base": "B 基地", "empty": true, "spec": "600*1200"}
```

## 🔴 铁律

1. **仅处理 `base='B 基地'` 的产品**
2. **仅 400×800 规格**有B 基地产品，其他规格写空结果
3. **V6算法与某陶瓷企业一致**，仅窑炉参数不同（日产能31250箱）
5. **完成后必须写 `/tmp/schedule-b-result.json`**（包括空结果也要写）

> **⚠️ 输出中 d7/d30/d90 均为日均销量**（已除以天数），不是总量。

### 6. AI备注生成（通俗语言，工作人员可懂）

与 schedule-a 完全相同的生成规则，参考 schedule-a/SKILL.md 第6节。每条产品必须带 `ai_remark` 字段。
