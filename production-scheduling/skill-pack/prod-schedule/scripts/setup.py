#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
某陶瓷企业 金蝶SDK环境检测与安装
"""
import subprocess
import sys
import os

def check_sdk():
    """检测 SDK 是否已安装"""
    try:
        from k3cloud_webapi_sdk.main import K3CloudApiSdk
        return True, "SDK 已安装"
    except ImportError:
        return False, "SDK 未安装"

def install_sdk():
    """安装 SDK"""
    print("正在安装 kingdee.cdp.webapi.sdk>=8.2.0 ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "kingdee.cdp.webapi.sdk>=8.2.0"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("SDK 安装成功")
        return True
    else:
        print(f"SDK 安装失败: {result.stderr}")
        return False

def check_conf(config_path="conf.ini"):
    """检测配置文件是否存在"""
    if os.path.exists(config_path):
        return True, f"配置文件 {config_path} 存在"
    return False, f"配置文件 {config_path} 不存在，请复制 conf.ini.template 并填写账套信息"

def setup():
    """一键环境检测"""
    print("=" * 50)
    print("  某陶瓷企业 金蝶SDK环境检测")
    print("=" * 50)
    
    ok, msg = check_sdk()
    print(f"\n[SDK] {msg}")
    if not ok:
        print("请先安装SDK: pip install kingdee.cdp.webapi.sdk>=8.2.0")
    
    ok, msg = check_conf()
    print(f"[配置] {msg}")
    
    # 测试连接
    if ok:
        print("\n[连接测试]")
        try:
            from k3cloud_webapi_sdk.main import K3CloudApiSdk
            import json
            api = K3CloudApiSdk("https://<ERP 主机>/k3cloud/")
            api.Init(config_path='conf.ini', config_node='config')
            para = {
                "FormId": "BD_MATERIAL",
                "FieldKeys": "FName",
                "FilterString": "FName='HM4Z005'",
                "OrderString": "",
                "TopRowCount": 1,
                "StartRow": 0,
                "Limit": 1,
                "SubSystemId": ""
            }
            resp = api.ExecuteBillQuery(para)
            data = json.loads(resp)
            if isinstance(data, list) and len(data) > 0:
                print("  ✅ 金蝶连接正常")
            else:
                print("  ⚠️ 金蝶连接异常: " + str(data)[:200])
        except Exception as e:
            print(f"  ❌ 金蝶连接失败: {e}")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    setup()
