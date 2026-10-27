# IM 渠道 Logo

本目录用于存放各 IM 渠道的品牌 logo，文件命名约定：

```
/assets/im-channels/<slug>.png
```

`<slug>` 对应 `src/data/mock.ts → IMChannelConfig.slug`：

| slug      | 渠道     |
|-----------|----------|
| dingtalk  | 钉钉     |
| feishu    | 飞书     |
| lark      | Lark     |
| wechat    | 微信     |
| wecom     | 企业微信 |
| slack     | Slack    |
| whatsapp  | WhatsApp |

## 渲染逻辑

`Settings.tsx → ChannelLogo` 组件按 `slug` 拼路径加载图片：

- 图片存在 → 显示 logo（带淡入）
- 图片缺失 / 加载失败 → 自动回退到通用图标（`i-message`）+ 渠道色

因此当前即使本目录为空，渠道卡片也会正常渲染（回退到图标）。后续把各渠道 logo 放进来、保持文件名一致，**无需改代码**即自动替换。

## 建议规格

- 格式：PNG（透明背景）或 SVG
- 尺寸：建议 1:1，≥ 80×80 px（卡片内显示为 20×20，弹窗内 40×40）
- 命名严格小写，与上表 slug 一致
