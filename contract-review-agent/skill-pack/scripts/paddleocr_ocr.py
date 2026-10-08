#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaddleOCR-VL-1.6 视觉识别脚本 paddleocr_ocr.py
用途：对PDF/图片合同（扫描件）调用 PaddleOCR-VL API 做视觉分析（OCR+版面解析），
      输出 Markdown 文本与图片到指定目录。识别质量显著优于本地 tesseract，优先使用。
用法：
    python3 paddleocr_ocr.py <文件路径> [--out <输出目录>] [--interval 5] [--timeout 600]
支持：本地文件或 http(s) URL
输出：<输出目录>/doc_<页码>.md （Markdown文本）+ 版面图片
依赖：requests

API Token 配置（三选一，按优先级）：
  1) 环境变量  PADDLEOCR_TOKEN=<你的token>
  2) 配置文件  ~/.paddleocr_token （文件首行为 token，无换行符）
  3) 交互输入：首次运行时按提示粘贴 token（仅本次运行生效，不落盘）
未配置时脚本会明确报错，不会内置任何密钥。
"""

import json
import os
import sys
import time
import requests

JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
MODEL = "PaddleOCR-VL-1.6"


def get_token():
    """按 环境变量 -> ~/.paddleocr_token 文件 -> 交互输入 顺序获取 API Token。"""
    tok = os.environ.get("PADDLEOCR_TOKEN", "").strip()
    if tok:
        return tok
    cfg = os.path.expanduser("~/.paddleocr_token")
    if os.path.exists(cfg):
        with open(cfg, encoding="utf-8") as f:
            tok = f.readline().strip()
        if tok:
            return tok
    print("未配置 PaddleOCR API Token。请任选一种方式：", file=sys.stderr)
    print("  ① export PADDLEOCR_TOKEN=<你的token>", file=sys.stderr)
    print(f"  ② echo '<你的token>' > ~/.paddleocr_token", file=sys.stderr)
    tok = input("  ③ 或直接粘贴 token（仅本次生效，不落盘）：").strip()
    if not tok:
        sys.exit("错误：未提供 Token，无法调用 PaddleOCR-VL API。")
    return tok


def submit_job(file_path, headers):
    optional_payload = {
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": False,
    }
    if file_path.startswith("http"):
        headers["Content-Type"] = "application/json"
        payload = {
            "fileUrl": file_path,
            "model": MODEL,
            "optionalPayload": optional_payload,
        }
        resp = requests.post(JOB_URL, json=payload, headers=headers, timeout=60)
    else:
        if not os.path.exists(file_path):
            print(f"错误：文件不存在 {file_path}")
            sys.exit(1)
        data = {"model": MODEL, "optionalPayload": json.dumps(optional_payload)}
        with open(file_path, "rb") as f:
            resp = requests.post(JOB_URL, headers=headers, data=data,
                                 files={"file": f}, timeout=120)
    print(f"提交响应状态: {resp.status_code}")
    if resp.status_code != 200:
        print(f"响应内容: {resp.text}")
        sys.exit(1)
    job_id = resp.json()["data"]["jobId"]
    print(f"任务提交成功, job id: {job_id}")
    return job_id


def poll_job(job_id, headers, interval=5, timeout=600):
    url = f"{JOB_URL}/{job_id}"
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"查询失败: {resp.status_code} {resp.text}")
            time.sleep(interval)
            continue
        data = resp.json()["data"]
        state = data["state"]
        if state == "pending":
            print("任务状态: pending")
        elif state == "running":
            try:
                prog = data["extractProgress"]
                print(f"任务状态: running, 总页数 {prog['totalPages']}, 已提取 {prog['extractedPages']}")
            except KeyError:
                print("任务状态: running...")
        elif state == "done":
            prog = data["extractProgress"]
            print(f"任务完成: 提取页数 {prog['extractedPages']}, "
                  f"开始 {prog.get('startTime')}, 结束 {prog.get('endTime')}")
            return data["resultUrl"]["jsonUrl"]
        elif state == "failed":
            print(f"任务失败: {data.get('errorMsg')}")
            sys.exit(1)
        time.sleep(interval)
    print("超时：任务未在限定时间内完成")
    sys.exit(1)


def download_results(jsonl_url, out_dir):
    resp = requests.get(jsonl_url, timeout=120)
    resp.raise_for_status()
    lines = resp.text.strip().split("\n")
    os.makedirs(out_dir, exist_ok=True)
    page_num = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        result = json.loads(line)["result"]
        for res in result["layoutParsingResults"]:
            md_path = os.path.join(out_dir, f"doc_{page_num}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(res["markdown"]["text"])
            print(f"Markdown已保存: {md_path}")
            for img_path, img in res["markdown"]["images"].items():
                full_path = os.path.join(out_dir, img_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "wb") as f:
                    f.write(requests.get(img, timeout=60).content)
                print(f"图片已保存: {full_path}")
            for img_name, img in res["outputImages"].items():
                img_resp = requests.get(img, timeout=60)
                if img_resp.status_code == 200:
                    filename = os.path.join(out_dir, f"{img_name}_{page_num}.jpg")
                    with open(filename, "wb") as f:
                        f.write(img_resp.content)
                    print(f"图片已保存: {filename}")
            page_num += 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    file_path = sys.argv[1]
    out_dir = "output"
    interval = 5
    for i, a in enumerate(sys.argv):
        if a == "--out" and i + 1 < len(sys.argv):
            out_dir = sys.argv[i + 1]
        if a == "--interval" and i + 1 < len(sys.argv):
            interval = int(sys.argv[i + 1])

    headers = {"Authorization": f"bearer {get_token()}"}
    print(f"处理文件: {file_path}")
    job_id = submit_job(file_path, headers)
    jsonl_url = poll_job(job_id, headers, interval=interval)
    download_results(jsonl_url, out_dir)
    print(f"\n完成。识别结果目录: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    main()
