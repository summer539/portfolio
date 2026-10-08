# 排产输出格式设计 V2

**模板文件：** `assets/排产输出格式模板.xlsx`
**参考表格：** `2026年排产计划表(1)(1).xls` + AI排产数据融合

---

## 一、整体结构

每个规格一个 Sheet（由窑号区分），每 Sheet 按品牌分区块，最后附总计。

```
┌─ Sheet标题行 ───────────────────────────────────┐
│  {窑号}窑{规格} · 智能排产计划 · {日期}              │
├─ 品牌区块 × N ──────────────────────────────────┤
│  表头行（品牌|上线时间|编号|...|AI建议|...）          │
│  产品数据行                                        │
│  合计行                                            │
│  侧喷行（整行合并）                                 │
│  纸箱行（整行合并）                                 │
├─ 亮光总计 ──────────────────────────────────────┤
│  说明 + 制表人 + 日期                               │
└──────────────────────────────────────────────────┘
```

---

## 二、列定义（17列，品牌级排产明细）

| 列 | 标题 | 宽度 | 数据来源 | 说明 |
|:--:|------|:---:|------|------|
| A | 品牌 | 10 | 产品数据 | 品牌更变时合并单元格 |
| B | 上线时间 | 8 | 产品数据 | 顺序编号，同品牌合并 |
| C | 生产编号 | 20 | 产品数据 | |
| D | 备注 | 12 | Excel计划表 | 定制底标/工地定/优先做 |
| E | 计划库存(箱) | 10 | Excel计划表 | 营销表中的库存数 |
| F | 实时库存(箱) | 10 | ERP | 成品仓实时库存，**标红<500箱** |
| G | 营销排产 | 10 | Excel计划表 | 营销建议排产量 |
| H | AI排产 | 10 | V6算法 | AI建议排产量 |
| I | 近7天日均销量 | 10 | ERP | 日均出库（箱/天） |
| J | 近30天日均销量 | 10 | ERP | 日均出库（箱/天） |
| K | 近90天日均销量 | 10 | ERP | 日均出库（箱/天） |
| L | 底标 | 12 | 素材库 | "定制底标+"或空（合并） |
| M | 厚度 | 12 | 素材库+规格 | "7.3mm±0.2mm"等（合并） |
| N | 纸箱（图片） | 18 | 素材库 | 纸箱图片嵌入（合并） |
| O | 趋势 | 10 | V6 | 含图标 |
| P | AI备注 | 30 | V6 | 通俗中文排产原因 |

---

## 三、品牌区块内部行

### 3.1 表头行

```
品牌 | 上线时间 | 生产编号 | 备注 | 计划库存 | 实时库存 | 营销排产 | AI排产 | 生产数量 | 底标 | 厚度 | 纸箱名称 | 日均30d | 趋势 | AI备注
```

深蓝底(#002F54)，白色加粗字。

### 3.2 产品数据行

品牌名、上线时间、底标、厚度、纸箱（图片） 五列在品牌区块内合并单元格。

行高42pt，中文微软雅黑12pt，数字Times New Roman。

### 3.3 合计行

```
合计： | — | — | — | 计划库存总计 | 实时库存总计 | 营销总计 | AI总计 | — | — | — | — | — | — | —
```

浅蓝底(#D6E4F0)，加粗。

### 3.4 侧喷行（整行合并，左对齐）

格式来自素材库，品牌级固定：
```
侧喷：佛山高端定制、{品牌名}{系列名}、编号、日期
```
例：`侧喷：佛山高端定制、海恩迈瓷砖、编号、日期`

### 3.5 纸箱行（整行合并，左对齐）

格式来自素材库，品牌级固定：
```
纸箱：{片数}片{纸种}    纸箱名称：{纸箱名称}（{纸箱厂}）
```
例：`纸箱：七片牛皮纸      纸箱名称：海恩迈海岩（耀晨纸箱厂）`


```
```

---

## 四、Sheet尾部

### 亮光总计行
```
亮光总计：| — | — | — | 总计划库存 | 总实时库存 | 总营销排产 | 总AI排产 | — | — | — | — | — | — | —
```

### 说明行
```
说明：库存纸箱先用完，排产顺序按标注序号上线。定制产品需确认底标版本后再上线。
```

### 制表人行
```
制表人：{系统/人工}                                    日期：{YYYY年MM月DD日}
```

---

## 五、Sheet3 总结报告（跨基地合并）

保持现有21列布局（序号|基地|品牌|编号|规格|工艺|6月销量|7月销量|日均90d|日均30d|日均7d|计划库存|实时库存|营销建议|人工排产|AI建议|趋势|风险|优先级|vs营销|AI备注），并增加：

- 底部：双基地产能利用率、告急/积压 Top5
- 颜色：vs营销差异色（绿<10% / 黄10-50% / 红>50%）

---

## 六、素材库查询规范

### 6.1 位置

```
assets/brand-materials/{品牌名}/
```

### 6.2 查询方式

排产输出时，按品牌名查找素材目录，读取对应文件：

```python
import os
BASE = "assets/brand-materials"

def get_brand_material(brand, spec):
    """按品牌名获取素材，返回 {侧喷, 厚度, 底标, 纸箱材质, 纸箱名称}"""
    brand_dir = os.path.join(BASE, brand)
    if not os.path.isdir(brand_dir):
        return None  # 品牌未录入素材库
    
    result = {}
    
    # 侧喷 — 品牌级，多条目选第一条
    sp = os.path.join(brand_dir, "侧喷.txt")
    if os.path.exists(sp):
        with open(sp) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("品牌")]
            # 去掉"无侧喷"和纯"编号、日期"
            valid = [l for l in lines if l not in ("无侧喷", "编号、日期", "无")]
            result["侧喷"] = valid[0] if valid else ""
    
    # 厚度 — 按规格匹配（品牌级多规格）
    tp = os.path.join(brand_dir, "厚度.txt")
    if os.path.exists(tp) and spec:
        with open(tp) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("品牌")]
        # 规格→厚度映射
        CELL_COUNT = {"400×800":7, "600×1200":3, "750×1500":2, "800×800":3}
        thick_map = {
            "400×800": "7.3mm±0.2mm", "600×1200": "9.3mm±0.2mm",
            "750×1500": "10.0mm±0.2mm", "800×800": "10.0mm±0.2mm"
        }
        # 从素材库读取实际厚度，回退到默认值
        for line in lines:
            for s, t in thick_map.items():
                if t in line and s == spec:
                    thick_map[s] = line if "不低于" not in line else line
        result["厚度"] = thick_map.get(spec, "")
    
    # 底标 — 品牌级
    bl = os.path.join(brand_dir, "底标说明.txt")
    if os.path.exists(bl):
        with open(bl) as f:
            text = f.read()
            result["底标"] = "定制底标+" if "定制底标" in text else ""
    
    # 底标图片 — 取第一张
    bl_dir = os.path.join(brand_dir, "底标")
    if os.path.isdir(bl_dir):
        imgs = sorted([f for f in os.listdir(bl_dir) if f.endswith('.png')])
        result["底标图片"] = os.path.join(bl_dir, imgs[0]) if imgs else ""
    
    # 纸箱 — 品牌级（取纸箱名称，从纸箱说明文件读取）
    bx = os.path.join(brand_dir, "纸箱说明.txt")
    if os.path.exists(bx):
        with open(bx) as f:
            text = f.read()
            result["纸箱说明"] = text.strip()
    
    # 纸箱图片 — 取第一张
    bx_dir = os.path.join(brand_dir, "纸箱")
    if os.path.isdir(bx_dir):
        imgs = sorted([f for f in os.listdir(bx_dir) if f.endswith('.png')])
        result["纸箱图片"] = os.path.join(bx_dir, imgs[0]) if imgs else ""
    
    return result
```

### 6.3 在排产Excel中的使用

| 列 | 来源 | 查找方式 |
|:--:|------|---------|
| L 底标 | 素材库 | `get_brand_material(brand)["底标"]` |
| M 厚度 | 素材库+规格 | `get_brand_material(brand, spec)["厚度"]` |
| N 纸箱(图片) | 素材库 | `get_brand_material(brand)["纸箱图片"]` |
| 侧喷行 | 素材库 | `get_brand_material(brand)["侧喷"]` |
| 纸箱行 | 素材库+00汇总文件 | `get_brand_material(brand)["纸箱说明"]` |

### 6.4 触发条件

- **品牌在素材库中存在** → 自动读取并填入所有素材字段
- **品牌不在素材库中** → 该品牌区块不输出侧喷/纸箱行，底标/厚度列留空，日志警告
- **侧喷内容为"无侧喷"** → 侧喷行输出"编号、日期"
