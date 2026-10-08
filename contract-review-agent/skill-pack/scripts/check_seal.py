#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
印章检测脚本 check_seal.py
用途：审核PDF/图片合同（扫描件、盖章版）时，检测文件是否包含印章（公章/合同章）。
背景：电子版Word合同无法验证纸质盖章（须纸质确认）；但PDF/图片扫描件可通过颜色+形状分析检测。
用法：
    python3 check_seal.py <文件路径> [--dpi 200] [--pages all|1,2,3]
支持：PDF（fitz渲染）、PNG/JPG/JPEG/TIFF/BMP（PIL直接读取）
输出：每页检测结果（印章颜色/数量/位置）+ 总体结论
检测逻辑：
  1. 红色印章（常见公章）：R>140 且 G<100 且 B<100，像素数>阈值 且 呈团块分布
  2. 蓝色印章：B>100 且 B-R>60 且 B-G>30
  3. 深色印章（黑色/墨色章）：大面积深色连通块（宽高比接近圆形/方形，面积>2000px）
  4. 签章区检查：页面底部25%区域是否存在印章痕迹
注意：本脚本为辅助检测手段，无法替代纸质原件核验；结果仅供审核参考。
"""

import sys
import os
import numpy as np

def load_image(path, dpi=200):
    """加载图片，返回RGB numpy数组"""
    from PIL import Image
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        try:
            import fitz  # PyMuPDF
        except ImportError:
            print("错误：检测PDF需要 PyMuPDF (pip install pymupdf)")
            sys.exit(1)
        doc = fitz.open(path)
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(np.array(img))
        return pages, len(doc)
    else:
        img = Image.open(path).convert("RGB")
        return [np.array(img)], 1

def analyze_page(img):
    """分析单页，返回印章检测结果列表"""
    h, w = img.shape[:3][:2] if len(img.shape) == 3 else img.shape[:2]
    r = img[:, :, 0].astype(int)
    g = img[:, :, 1].astype(int)
    b = img[:, :, 2].astype(int)
    results = []

    # 1. 红色印章
    red_mask = (r > 140) & (g < 100) & (b < 100)
    red_n = int(red_mask.sum())
    if red_n > 300:  # 阈值：300像素以上视为疑似印章（200dpi下小印章约数千像素）
        ys, xs = np.where(red_mask)
        results.append(f"红色印章疑似: {red_n}px, 位置x[{xs.min()}-{xs.max()}] y[{ys.min()}-{ys.max()}]")

    # 2. 蓝色印章
    blue_mask = (b > 100) & (b - r > 60) & (b - g > 30)
    blue_n = int(blue_mask.sum())
    if blue_n > 300:
        ys, xs = np.where(blue_mask)
        results.append(f"蓝色印章疑似: {blue_n}px, 位置x[{xs.min()}-{xs.max()}] y[{ys.min()}-{ys.max()}]")

    # 3. 深色印章（黑色/墨色）：找大面积深色连通块
    dark = (r < 120) & (g < 120) & (b < 120)
    dark_n = int(dark.sum())
    if dark_n > 0:
        # 简单连通域分析（BFS，避免scipy依赖）
        visited = np.zeros_like(dark, dtype=bool)
        big_blocks = []
        ys, xs = np.where(dark)
        # 采样遍历（全量BFS在低分辨率下可接受）
        for y, x in zip(ys, xs):
            if visited[y, x]:
                continue
            # BFS
            stack = [(y, x)]
            visited[y, x] = True
            count = 0
            min_y = max_y = y
            min_x = max_x = x
            while stack:
                cy, cx = stack.pop()
                count += 1
                if cy < min_y: min_y = cy
                if cy > max_y: max_y = cy
                if cx < min_x: min_x = cx
                if cx > max_x: max_x = cx
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and dark[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((ny, nx))
            if count > 2000:
                bw = max_x - min_x
                bh = max_y - min_y
                ratio = bw / bh if bh > 0 else 0
                # 印章通常宽高比0.6~1.8（圆形/方形），且尺寸适中（印章直径约150-600px@200dpi）
                if 0.5 <= ratio <= 2.0 and 100 <= bw <= 1200 and 100 <= bh <= 1200:
                    big_blocks.append((count, min_x, max_x, min_y, max_y, ratio))
        if big_blocks:
            big_blocks.sort(key=lambda x: -x[0])
            for count, min_x, max_x, min_y, max_y, ratio in big_blocks[:3]:
                results.append(
                    f"深色印章疑似: {count}px, 尺寸{max_x-min_x}x{max_y-min_y}, "
                    f"宽高比{ratio:.2f}, 位置x[{min_x}-{max_x}] y[{min_y}-{max_y}]"
                )

    # 4. 签章区检查（页面底部25%区域）
    bot = dark[int(h * 0.75):, :]
    bot_n = int(bot.sum())
    bottom_note = f"签章区(底部25%)深色像素: {bot_n}px"
    if bot_n < 500:
        bottom_note += " → 签章区基本空白，未见盖章痕迹"
    results.append(bottom_note)

    return results

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    dpi = 200
    for i, a in enumerate(sys.argv):
        if a == '--dpi' and i + 1 < len(sys.argv):
            dpi = int(sys.argv[i + 1])

    if not os.path.exists(path):
        print(f"错误：文件不存在 {path}")
        sys.exit(1)

    pages, n = load_image(path, dpi)
    print(f"文件: {path}")
    print(f"页数: {n}")

    total_red = total_blue = total_dark_blocks = 0
    for i, img in enumerate(pages):
        res = analyze_page(img)
        has_seal = any('印章疑似' in x for x in res)
        print(f"\n--- 第{i+1}页 ---")
        for x in res:
            print(f"  {x}")
        if has_seal:
            total_red += sum('红色' in x for x in res)
            total_blue += sum('蓝色' in x for x in res)
            total_dark_blocks += sum('深色印章' in x for x in res)

    print("\n===== 总体结论 =====")
    if total_red + total_blue + total_dark_blocks == 0:
        print("未检测到印章（无红/蓝/深色印章图形）。")
        print("提示：①可能为未盖章的电子文档/扫描件；②'（盖章）'仅为打印字样时盖章处为空；")
        print("      ③如有手写笔迹而印章缺失，说明已签字未盖章；④纸质原件核验不可替代。")
    else:
        print(f"检测到疑似印章: 红色{total_red}处, 蓝色{total_blue}处, 深色{total_dark_blocks}处")
        print("提示：印章检测为辅助手段，请结合原件核验印章真实性（防伪、骑缝章等）。")

if __name__ == '__main__':
    main()
