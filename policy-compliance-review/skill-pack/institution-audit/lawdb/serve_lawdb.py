#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法规库本地预览服务
- 动态读取 law.db：数据库有更新（新法规注入）时，页面自动重新生成
- 前端每 8 秒轮询 /api/meta，检测到数据库版本变化后自动刷新，无需手动操作
用法:
  python3 lawdb/serve_lawdb.py             # 默认 0.0.0.0:8317
  python3 lawdb/serve_lawdb.py --port 9000
"""
import os, sys, sqlite3, json, subprocess, argparse, time
from flask import Flask, Response, jsonify

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "law.db")
PREVIEW = os.path.join(BASE, "preview.html")
GEN = os.path.join(BASE, "preview_lawdb.py")

app = Flask(__name__)
cache = {"key": None, "html": None, "meta": None}


def db_key():
    st = os.stat(DB)
    return f"{st.st_mtime_ns}-{st.st_size}"


def db_stats():
    con = sqlite3.connect(DB)
    laws = con.execute("SELECT COUNT(*) FROM laws").fetchone()[0]
    arts = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    con.close()
    return laws, arts


def ensure_fresh():
    """数据库版本变化时重新生成预览页面并缓存"""
    key = db_key()
    if cache["key"] != key:
        # preview.html 存在且不比 law.db 旧时直接复用，避免每次启动重新生成（约 3 分钟）
        if os.path.exists(PREVIEW) and os.stat(PREVIEW).st_mtime >= os.stat(DB).st_mtime:
            with open(PREVIEW, encoding="utf-8") as f:
                html = f.read()
        else:
            subprocess.run([sys.executable, GEN, PREVIEW],
                           check=True, capture_output=True)
            with open(PREVIEW, encoding="utf-8") as f:
                html = f.read()
        laws, arts = db_stats()
        updated_at = time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.localtime(os.stat(DB).st_mtime))
        ver = key
        # 注入自动刷新脚本：轮询 /api/meta，版本变化即整页刷新
        script = f"""<script>
const DB_VERSION = {json.dumps(ver)};
async function checkUpdate(){{
  try {{
    const r = await fetch('/api/meta', {{cache:'no-store'}});
    const m = await r.json();
    if (m.version !== DB_VERSION) location.reload();
  }} catch(e) {{}}
}}
setInterval(checkUpdate, 8000);
</script>"""
        html = html.replace("</body>", script + "</body>")
        cache.update(key=key, html=html,
                     meta={"version": ver, "laws": laws, "articles": arts,
                           "updated_at": updated_at,
                           "db_file": os.path.basename(DB)})
        print(f"[{time.strftime('%H:%M:%S')}] 数据库已更新，预览已重新生成 "
              f"({laws} 部 / {arts} 条)", flush=True)
    return cache


@app.route("/")
def index():
    c = ensure_fresh()
    return Response(c["html"], mimetype="text/html")


@app.route("/api/meta")
def meta():
    c = ensure_fresh()
    return jsonify(c["meta"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="法规库本地预览服务")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8317)
    args = ap.parse_args()
    print(f"📚 法规库预览服务启动: http://{args.host}:{args.port}/", flush=True)
    app.run(host=args.host, port=args.port, threaded=True)
