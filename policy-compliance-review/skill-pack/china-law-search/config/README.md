# 配置说明（Config）

对接系统环境的配置文件与运行时说明。

## 文件清单

| 文件 | 用途 |
|---|---|
| `playwright-config.json` | playwright-cli 浏览器配置。root 环境下 Chromium 需禁用沙箱（`chromiumSandbox: false`），否则 `playwright-cli open` 报 `Chromium sandboxing failed!` |
| `requirements.txt` | Python 依赖清单（核心零依赖，可选 openpyxl 等） |
| 本文件 | 安装对接说明 + athenaappkey 手动刷新流程 |

## 环境要求

- Python 3.8+（核心查询仅标准库）
- 可选：`openpyxl`（Excel 导入/导出）、`pandoc` + `python-docx`（规章库转 docx）
- 可选：`@playwright/cli`（npm 包，规章库密钥自动刷新 / flk 签名下载 / 香港法例渲染；首次使用时 `gov_api.py` 自动安装）

## 运行时生成文件（不入库）

- `scripts/lib/.athena_key_cache.json` — 规章库 athenaappkey 缓存（自动生成，约 1 小时过期，自动刷新）
- `.playwright-cli/` — playwright-cli 运行日志缓存（自动生成）

## athenaappkey 手动刷新标准流程（自动刷新失败时）

**Step 1：打开规章库页面**
```bash
cd <技能安装路径>/china-law-search && playwright-cli --config=config/playwright-config.json open https://www.gov.cn/zhengce/xxgk/gjgzk/index.htm
```

**Step 2：拦截请求获取 key**
```bash
playwright-cli --raw run-code "async page => {
  const keys = [];
  await page.route(url => url.href.includes('athena/forward'), async route => {
    const key = route.request().headers()['athenaappkey'] || '';
    if (key) keys.push(key);
    await route.continue();
  });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  await page.unroute(url => url.href.includes('athena/forward'));
  return keys.join(',');
}"
```
输出是逗号分隔的多个 key（都一样），取第一个即可。

**Step 3：保存到缓存文件**
```python
import json, time
key = '这里粘贴Step2输出的第一个key'
cache_path = '<技能安装路径>/china-law-search/scripts/lib/.athena_key_cache.json'
with open(cache_path, 'w') as f:
    json.dump({'key': key, 'ts': time.time()}, f)
```

**Step 4：关闭浏览器**
```bash
playwright-cli close
```

> 注意：`--config` 仅对 `open` 命令有效；run-code/close 走已启动的 daemon socket，不接受 `--config`（会报 `Unknown option: --config`）。

## 香港法规访问配置（沙箱环境）

- 港交所规则网：`cn-rules.hkex.com.hk` 沙箱直连失败，需走代理前缀 `https://sc.hkex.com.hk/TuniS/<原URL>`
- 香港法例 e-legislation.gov.hk：对 requests/curl 有客户端检测，需 playwright-cli 渲染
