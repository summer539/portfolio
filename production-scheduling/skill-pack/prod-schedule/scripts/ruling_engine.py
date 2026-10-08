#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排产审批引擎 V6.0
多时间维度耦合缺口裁决法 — 7天/30天/90天 梯度趋势驱动
"""
import math

# 常量
MIN_BATCH = 1500     # 最低批次
NEW_MIN = 3000       # 新品首排

# 排产批次档位
BATCHES = [1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000,
           5500, 6000, 6500, 7000, 8000, 9000, 10000]

# ── 规格 → 窑号 → 日产能 ──
# 箱/天 = 日产能(㎡) ÷ FVolume(㎡/箱), FVolume通过BD_MATERIAL.FVolume查询
# 淡季上限 = 日产能(箱), 旺季上限 = 日产能(箱)（不设淡旺季产能上限，统一满产）
KILN_CAPACITY = {
    # 规格          窑号   日产能㎡  FVolume  日产能箱  片/箱  单片㎡   基地
    '400*800':  {'kiln': '3号窑', 'sqm': 38000, 'vol': 2.24, 'daily': 16964, 'pcs': 7, 'tile': 0.32, 'base': '某陶瓷企业'},
    '400*800-b': {'kiln': 'B 基地窑','sqm': 70000, 'vol': 2.24, 'daily': 31250, 'pcs': 7, 'tile': 0.32, 'base': 'B 基地'},
    '600*1200': {'kiln': '2号窑', 'sqm': 38000, 'vol': 2.16, 'daily': 17593, 'pcs': 3, 'tile': 0.72, 'base': '某陶瓷企业'},
    '600*1201': {'kiln': '2号窑', 'sqm': 38000, 'vol': 2.16, 'daily': 17593, 'pcs': 3, 'tile': 0.72, 'base': '某陶瓷企业'},
    '750*1500': {'kiln': '1号窑', 'sqm': 26000, 'vol': 2.25, 'daily': 11556, 'pcs': 2, 'tile': 1.125, 'base': '某陶瓷企业'},
    '750*1501': {'kiln': '1号窑', 'sqm': 26000, 'vol': 2.25, 'daily': 11556, 'pcs': 2, 'tile': 1.125, 'base': '某陶瓷企业'},
    '800*800':  {'kiln': '5号窑', 'sqm': 26000, 'vol': 1.92, 'daily': 13542, 'pcs': 3, 'tile': 0.64, 'base': '某陶瓷企业'},
}

DEFAULT_DAILY = 8000  # 未匹配规格时的兜底日产能

# 季节系数：不分淡旺季，统一满产
SEASON_RATIO = 1.0     # 统一满产


# ════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════

def _next_batch(target):
    """返回 ≥ target 的最小批次"""
    for b in BATCHES:
        if b >= target:
            return b
    return BATCHES[-1]


def _prev_batch(target):
    """返回 ≤ target 的最大批次"""
    for b in reversed(BATCHES):
        if b <= target:
            return b
    return MIN_BATCH


def get_kiln_cap(spec, base='某陶瓷企业'):
    """根据规格返回对应窑炉日产能（箱/天）"""
    # B 基地 400×800 用独立窑
    if base == 'B 基地' and spec and spec.replace('*','').startswith('400'):
        return KILN_CAPACITY['400*800-b']['daily']
    info = KILN_CAPACITY.get(spec)
    if info and info.get('base') == base:
        return info['daily']
    for key, val in KILN_CAPACITY.items():
        if spec and key and spec[:2] == key[:2] and val.get('base') == base:
            return val['daily']
    return DEFAULT_DAILY


def get_season_cap(spec, plan_month, base='某陶瓷企业'):
    """返回单产品排产上限（不设淡旺季限制，统一满产）"""
    daily = get_kiln_cap(spec, base)
    return round(daily / 500) * 500


# ════════════════════════════════════════════
#  趋势判断 — 三时间维度梯度
# ════════════════════════════════════════════

def judge_trend(d7, d30, d90):
    """
    7天/30天/90天 三者梯度关系判断产品状态
    
    参数:
      d7:  近7天日均销量
      d30: 近30天日均销量
      d90: 近90天日均销量
    
    返回: (trend_label, trend_icon)
      加速上涨🔥 回暖上涨📈 平稳➡️ 降温📉 持续衰减⬇️ 脉冲波动⚡
    """
    if d7 <= 0 and d30 <= 0:
        return '平稳', '➡️'
    
    # 脉冲检测：7天与30天偏离超过2倍
    if d30 > 0 and d7 > 0:
        if d7 > d30 * 2.0:
            return '脉冲波动', '⚡'
        if d7 < d30 * 0.3:
            return '脉冲波动', '⚡'
    
    # 三级梯度判断
    if d7 > 0 and d30 > 0 and d90 > 0:
        if d7 > d30 > d90 * 1.2:
            return '加速上涨', '🔥'
        if d7 < d30 < d90:
            return '持续衰减', '⬇️'
    
    if d7 > 0 and d30 > 0 and d90 > 0:
        if d7 > d30 and abs(d30 - d90) / max(d90, 1) < 0.2:
            return '回暖上涨', '📈'
        if d7 < d30 * 0.7:
            return '降温', '📉'
    
    # 缺90天数据时的降级判断
    if d7 > 0 and d30 > 0 and d90 <= 0:
        if d7 > d30 * 1.3:
            return '回暖上涨', '📈'
        elif d7 < d30 * 0.7:
            return '降温', '📉'
    
    return '平稳', '➡️'


# ════════════════════════════════════════════
#  V6 裁决引擎
# ════════════════════════════════════════════

def calculate_p(s_cycle, inventory, M, plan_month, is_new=False, spec='',
                s_30d=0, s_90d=0, base='某陶瓷企业'):
    """
    V6 多时间维度耦合缺口裁决法
    
    7天→即时缺口底线 | 30天→过滤异常确认度 | 90天→边界安全阀
    
    Step 1: 日均销量 d7, d30, d90
    Step 2: 三级梯度趋势判定
    Step 3: 双 gap 取大（gap_7 vs gap_weighted），脉冲波动屏蔽7天
    Step 4: 趋势加成 — 批次档位跳跃
    Step 5: 90天安全阀 + 产能硬约束 + 批次约束
    
    参数:
      s_cycle:   近7天销量
      inventory: 当前库存
      M:         营销建议排产量
      plan_month: 计划月份
      is_new:    是否新品
      spec:      规格如'400*800'
      s_30d:     近30天销量（0=跳过）
      s_90d:     近90天销量（0=跳过）
    
    返回: (P, reason, verdict, season_cap, trend_label)
    """
    # S1: 日均
    d7  = s_cycle / 7.0 if s_cycle > 0 else 0
    d30 = s_30d / 30.0 if s_30d > 0 else 0
    d90 = s_90d / 90.0 if s_90d > 0 else 0
    
    # S2: 趋势
    trend_label, trend_icon = judge_trend(d7, d30, d90)
    
    # S3: 双 gap 取大
    gap_7 = max(0, s_cycle - inventory)
    
    if d30 > 0:
        d_weighted = 0.5 * d7 + 0.3 * d30
        d_weighted += 0.2 * d90 if d90 > 0 else 0
        if d90 <= 0:
            d_weighted = 0.6 * d7 + 0.4 * d30
    else:
        d_weighted = d7
    
    gap_weighted = max(0, d_weighted * 7 - inventory)
    
    if trend_label == '脉冲波动' and d30 > 0:
        effective_gap = max(0, d30 * 7 - inventory)
        gap_source = '30天（屏蔽7天脉冲）'
    else:
        effective_gap = max(gap_7, gap_weighted, 0)
        gap_source = 'max(7天, 加权)'
    
    # 新品无历史
    if is_new and effective_gap <= 0 and s_cycle <= 0:
        P = NEW_MIN
        season_cap = get_season_cap(spec, plan_month, base)
        P = min(P, season_cap)
        return P, '新品首排，无历史数据，按最低批次3000箱', '✅ 批准（新品）', season_cap, trend_label
    
    # S4: 趋势加成
    if effective_gap > 0:
        base_P = _next_batch(effective_gap)
        
        if trend_label == '加速上涨':
            base_P = max(base_P, _next_batch(max(0, d_weighted * 10 - inventory)))
        elif trend_label == '回暖上涨':
            base_P = max(base_P, _next_batch(max(0, d_weighted * 8 - inventory)))
        elif trend_label in ('持续衰减', '降温'):
            if d30 > 0:
                base_P = max(_next_batch(max(0, d30 * 7 - inventory)), MIN_BATCH)
            base_P = max(base_P, MIN_BATCH)
        elif trend_label == '脉冲波动' and d30 > 0:
            base_P = max(_next_batch(max(0, d30 * 7 - inventory)), MIN_BATCH)
    else:
        # gap = 0: 库存充足
        if is_new:
            base_P = NEW_MIN
        elif s_cycle > 0 and M <= s_cycle * 3:
            base_P = M
            if trend_label in ('持续衰减', '降温'):
                base_P = max(MIN_BATCH, _next_batch(d30 * 3) if d30 > 0 else MIN_BATCH)
        elif s_cycle > 0 and M > s_cycle * 3:
            base_P = M  # 人工决断
        elif d30 > 0:
            if trend_label in ('持续衰减', '降温'):
                base_P = max(MIN_BATCH, _next_batch(d30 * 3))
            else:
                base_P = max(MIN_BATCH, _next_batch(d30 * 7))
        else:
            base_P = MIN_BATCH
    
    P = base_P
    
    # S5: 90天安全阀
    safety_flag = ''
    if d90 > 0:
        ceiling_90 = max(d90 * 60, NEW_MIN)
        if P > ceiling_90:
            old_P = P
            P = _prev_batch(ceiling_90)
            safety_flag = f'（触及90天上限，P从{old_P}压降至{P}）'
        if d30 > d90 and P < d30 * 7 - inventory and d30 * 7 > inventory:
            P = _next_batch(max(0, d30 * 7 - inventory))
            safety_flag += '（上穿校正：近30天趋势高于90天基线）'
    
    # S6: 产能 + 批次 + 取整
    season_cap = get_season_cap(spec, plan_month, base)
    cap_flag = ''
    if P > season_cap:
        old_P = P
        P = season_cap
        cap_flag = f'（触及窑炉产能上限，从{old_P}压降至{P}）'
    
    if is_new and P < NEW_MIN:
        P = NEW_MIN
    elif P < MIN_BATCH:
        P = MIN_BATCH
    
    P = round(P / 500) * 500
    if P < 500:
        P = 500
    
    # ── 裁决文案 ──
    if effective_gap > 0:
        if M >= P:
            reason = (f'库存缺口{effective_gap:.0f}箱（{gap_source}），'
                      f'趋势{trend_label}{trend_icon}，营销建议{M}箱已覆盖，批准')
            verdict = '✅ 批准'
        else:
            reason = (f'库存缺口{effective_gap:.0f}箱（{gap_source}），'
                      f'趋势{trend_label}{trend_icon}，营销建议{M}箱不足，'
                      f'建议上调至{P}箱')
            verdict = f'⚠️ 建议上调至{P}箱'
    else:
        if s_cycle > 0 and M > s_cycle * 3 and trend_label in ('加速上涨', '回暖上涨'):
            reason = (f'库存充足（{inventory:.0f}箱），趋势{trend_label}{trend_icon}，'
                      f'营销建议{M}箱偏高于近7天销量3倍但趋势支撑，批准')
            verdict = '✅ 批准'
        elif s_cycle > 0 and M > s_cycle * 3:
            reason = (f'库存充足（{inventory:.0f}箱），趋势{trend_label}{trend_icon}，'
                      f'营销建议{M}箱偏高（超过近7天销量3倍），请人工确认')
            verdict = '⚠️ 建议量偏高，待确认'
        elif trend_label in ('持续衰减', '降温') and P < M:
            reason = (f'库存充足（{inventory:.0f}箱），趋势{trend_label}{trend_icon}，'
                      f'建议压降至{P}箱以控制库存风险')
            verdict = f'✅ 批准（调低至{P}箱）'
        else:
            reason = (f'库存充足（{inventory:.0f}箱），趋势{trend_label}{trend_icon}，'
                      f'可覆盖近7天销量（{s_cycle:.0f}箱），批准')
            verdict = '✅ 批准'
    
    if safety_flag or cap_flag:
        reason += f' {safety_flag}{cap_flag}'
    
    return P, reason, verdict, season_cap, trend_label


# ════════════════════════════════════════════
#  风险标记
# ════════════════════════════════════════════

def mark_risk(daily_sales, inventory, inventory_days, trend_label):
    """
    根据库存、日均销量、趋势判断风险等级
    
    参数:
      daily_sales:    日均销量（推荐用 d_weighted）
      inventory:      当前库存
      inventory_days: 库存可支撑天数
      trend_label:    趋势标签 ('加速上涨','回暖上涨','平稳','降温','持续衰减','脉冲波动')
    
    返回: (risk_label, risk_icon) 或 (None, None)
    """
    # 零库存告急
    if inventory == 0 and daily_sales > 5:
        return '告急', '🚨'
    # 库存极低
    if inventory_days < 3 and daily_sales > 0:
        return '告急', '🚨'
    # 库存偏低
    if inventory_days < 10:
        return '偏低', '🔥'
    # 严重积压
    if inventory_days > 60 and inventory > 500:
        return '积压', '⛔'
    # 销量断崖
    if trend_label == '持续衰减' and daily_sales > 5:
        return '骤降', '📉'
    # 突然放量
    if trend_label == '加速上涨' and daily_sales > 20:
        return '激增', '📈'
    return None, None


# ════════════════════════════════════════════
#  优先级评分
# ════════════════════════════════════════════

def calc_priority(inventory, inventory_days, is_custom, is_new, d30, d90):
    """
    计算产品排产优先级（0-1之间，越高越优先）
    
    参数:
      inventory:       当前库存
      inventory_days:  库存可支撑天数
      is_custom:       是否定制产品
      is_new:          是否新品
      d30:             近30天日均
      d90:             近90天日均
    
    返回: float 优先级分数
    """
    # 库存紧迫度
    urgency = 1.0 / (inventory_days + 1)
    
    # 客户等级
    customer_level = 1.0 if is_custom else 0.5
    
    # 销量趋势（归一化到0-1）
    if d90 > 0:
        trend_ratio = min(2.0, d30 / d90) / 2.0
    else:
        trend_ratio = 0.5
    
    # 特殊标记
    if is_custom:
        special = 0.5
    elif is_new:
        special = 0.5
    else:
        special = 0.0
    
    priority = 0.4 * urgency + 0.3 * customer_level + 0.2 * trend_ratio + 0.1 * special
    return round(priority, 4)


# ════════════════════════════════════════════
#  营销参照规则
# ════════════════════════════════════════════

def apply_marketing_ref(P, marketing_plan, inventory_days, inventory, trend_label):
    """
    应用营销参照规则，防止过度缩减
    
    参数:
      P:              当前AI建议排产量
      marketing_plan: 营销建议排产量
      inventory_days: 库存可支撑天数
      inventory:      当前库存
      trend_label:    趋势标签
    
    返回: 调整后的P
    """
    # 库存紧缺，不能缩减超过30%
    if inventory_days < 10:
        P = max(P, marketing_plan * 0.7)
    
    # 库存严重积压，最多排50%
    if inventory_days > 90 and inventory > 500:
        P = min(P, marketing_plan * 0.5)
    
    # 持续衰减且库存多，最多排60%
    if trend_label == '持续衰减' and inventory > 200:
        P = min(P, marketing_plan * 0.6)
    
    return P
