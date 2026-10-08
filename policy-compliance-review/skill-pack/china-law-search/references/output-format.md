# 查询结果格式与转换模板（Output Format）

## 一、统一输出字段说明

所有查询结果统一包含以下字段：

| 字段 | 说明 |
|---|---|
| title | 法规名称 |
| type / flxz | 法规类别（法律/行政法规/部门规章/地方政府规章等） |
| date / gbrq | 公布日期 |
| status / sxx_text | 状态（有效/已修改/已废止/尚未生效） |
| org / zdjgName | 制定机关 |
| source | 数据来源：`国家法律法规数据库` 或 `国家规章库` |
| url | 原文链接（可点击） |

## 二、unified_batch_check 返回格式

返回 list，每个元素是 dict，包含 `name`, `found`, `title`, `status`, `bbbs`, `url`, `flxz`, `source` 等字段：

```json
[
  {"name": "安全生产法", "found": true, "title": "中华人民共和国安全生产法",
   "status": "有效", "bbbs": "xxx", "url": "https://flk.npc.gov.cn/...",
   "flxz": "法律", "source": "国家法律法规数据库"},
  {"name": "某指引", "found": false, "status": "未找到（搜索结果不匹配）"}
]
```

- `found=True` 时有完整信息；`found=False` 时只有 `name` 和 `status`
- **注意**：规章库结果的 `status` 是 `"有效（规章库）"`，`source` 是 `"gov.cn"`

## 三、转成 batch_download_from_check 需要的格式

```python
import json

# Step 1: 批量查询
results = law_search.unified_batch_check(["法规名称1", "法规名称2"])

# Step 2: 转成 {法规名: {status, url, source, ...}} 格式
check_progress = {}
for r in results:
    name = r.get("name", "")
    check_progress[name] = {
        "status": r.get("status", ""),
        "url": r.get("url", ""),
        "source": "国家规章库" if r.get("source") == "gov.cn" else "国家法律法规数据库",
    }

# Step 3: 批量下载（支持断点续下）
law_search.batch_download_from_check(
    check_progress=check_progress,
    output_dir="./下载",
    delay=0.5,
    dl_progress_file="download_progress.json",
)

# Step 4: 如有超时，直接重跑（自动跳过已下载的）
law_search.batch_download_from_check(
    check_progress=check_progress,
    output_dir="./下载",
    delay=0.5,
    dl_progress_file="download_progress.json",
)
```

## 四、文件命名模板

下载文件命名: `法规类型_法规名称_公布日期_状态.ext`

```
法律_中华人民共和国安全生产法_2021-06-10_有效.docx
```
