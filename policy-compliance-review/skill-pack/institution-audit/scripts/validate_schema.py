#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基础审核结果结构校验。"""
import argparse, json

def validate(data):
    errors = []
    for i, item in enumerate(data if isinstance(data, list) else [data]):
        result = item.get("result")
        if result not in ("可以不改", "必须改", "NEED_LIBRARY_SUPPLEMENT"):
            errors.append(f"[{i}] result 不合法")
        if result == "可以不改" and item.get("issues"):
            errors.append(f"[{i}] 可以不改时 issues 必须为空")
        if result == "必须改":
            for key in ("error_type", "problem", "suggestion"):
                if not item.get(key): errors.append(f"[{i}] 必须改缺少 {key}")
            if not item.get("basis_article_ids"):
                errors.append(f"[{i}] 必须改缺少 basis_article_ids")
            if item.get("grounding_status") != "PASSED":
                errors.append(f"[{i}] 必须改的 grounding_status 必须为 PASSED")
    return errors

def main():
    p=argparse.ArgumentParser(); p.add_argument("json"); args=p.parse_args()
    with open(args.json, encoding="utf-8") as f: data=json.load(f)
    errors=validate(data)
    if errors:
        for e in errors: print("ERROR", e)
        raise SystemExit(1)
    print("Schema 校验通过")
if __name__ == "__main__": main()
