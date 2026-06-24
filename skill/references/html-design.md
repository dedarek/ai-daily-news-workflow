# HTML 邮件设计规范

参考模板文件：`templates/v4-2026-03-18.html`

## 核心设计原则
- **亮色安全方案**：标题栏用蓝色 `#3b82f6`（不使用深色背景 `#0F172A`），确保在 Outlook 亮色和暗色主题下均清晰可见
- **所有文字颜色必须不依赖深色背景**：不用 `#ffffff` 或 `#9CA3AF` 等需要深色衬托的颜色
- **每条新闻都必须有底部原文链接**，格式为 `🔗 完整URL`
- **每期12-15条**，每个栏目2-3条，精选最重要的

## 整体结构
```
┌─────────────────────────────┐
│  Header（蓝色背景 #3b82f6）   │
│  📰 每日AI热点新闻（试运营）    │
│  YYYY年MM月DD日 星期X          │
├─────────────────────────────┤
│  AI 总结（白底，无标签前缀）     │
│  3-5句话概括今日最重要事件        │
├─────────────────────────────┤
│  🔥 今日焦点（蓝色下划线 #dbeafe）│
│  ┌─────────────────────────┐│
│  │ [焦点标签] 新闻标题（蓝色链接）││
│  │ 正文（#475569，≥4句话）     ││
│  │ AI锐评（#fffbeb底，左border）││
│  │ 🔗 https://example.com   ││
│  └─────────────────────────┘│
├─────────────────────────────┤
│  🚀 产品发布                    │
│  ┌─────────────────────────┐│
│  │ 新闻卡片（#f8fafc底，1px边框）││
│  │ ...                      ││
│  └─────────────────────────┘│
├─────────────────────────────┤
│  Footer（#edf0f4 背景）       │
│  联系方式（#64748b文字，#2563EB链接）│
└─────────────────────────────┘
```

## HTML 实现要求（必须用 table 布局）

关键规范：
- 外层 body 背景用 `#eef1f5`
- 主容器 `width="700"`，白底 `#ffffff`，`border:1px solid #c9cdd4`，`border-radius:10px`
- 标题栏背景 `#3b82f6`，底边框 `border-bottom:4px solid #1d4ed8`，标题白字 `#ffffff`，日期 `rgba(255,255,255,0.85)`
- 摘要区：`color:#374151`，`font-size:15px`，`line-height:1.9`
- 栏目标题：`color:#111827`，`border-bottom:2px solid #dbeafe`
- 每条新闻用独立 table 卡片：`border:1px solid #e5e7eb`，`border-radius:8px`，`background-color:#f8fafc`
- 焦点新闻：`border:1px solid #fca5a5`，`border-left:4px solid #ef4444`
- AI锐评用嵌套 table：`background-color:#fffbeb`，`border-left:3px solid #f59e0b`
- 标题用 `<a>` 蓝色链接 `#2563EB`
- 底部URL：`font-size:12px`，`color:#64748b`，链接 `#2563EB`，显示完整URL
- Footer：`background-color:#edf0f4`，`border-top:2px solid #d1d5db`，文字 `#64748b`，链接 `#2563EB`

## Footer 内容
- 必须居中：`text-align: center`
- 第一行：`联系我们：penglei4@lenovo.com ｜ yangyc13@lenovo.com`（均为 mailto 链接，颜色 #2563EB）
- 第二行：`技术创新中心：-TIC@lenovo.com`（mailto 链接，颜色 #2563EB）
- 禁止出现"仅供参考"、"如需退订请联系管理员"、"本邮件由 AI 自动生成"等字样
- ⛔ 参考 `/tmp/ai-daily-news-html-2026-04-10.html` 中的 footer 写法（2026-04-12 确认为正确格式）

## 配色与字体规范
| 元素 | 颜色 | 字号 | 字重 |
|------|------|------|------|
| 标题栏背景 | **#3b82f6** | — | — |
| 标题栏底边 | #1d4ed8 | — | — |
| 标题文字 | #FFFFFF | 22px | Bold |
| 日期文字 | rgba(255,255,255,0.85) | 13px | Regular |
| AI总结正文 | #374151 | 15px | Regular |
| 栏目标题 | #111827 | 17px | Bold |
| 栏目下划线 | #dbeafe | 2px | — |
| 新闻标题 | #2563EB（链接色） | 15px | Bold |
| 新闻正文 | #475569 | 14px | Regular |
| AI锐评 | #6B7280 | 13px | Italic，左border #f59e0b |
| 锐评背景 | #fffbeb | — | — |
| 原文链接 | #64748b 文字，#2563EB 链接 | 12px | Regular |
| 卡片背景 | #f8fafc | — | — |
| 卡片边框 | #e5e7eb | 1px | — |
| 主容器边框 | #c9cdd4 | 1px | — |
| Footer 背景 | #edf0f4 | — | — |
| Footer 文字 | #64748b | 12px | Regular |
| 焦点标签 | #ef4444 | 11px | Bold，白字圆角 |
| 焦点边框 | #fca5a5 + #ef4444左边 | — | — |

## 字体
- 中文：PingFang SC, Microsoft YaHei, sans-serif
- 英文：Inter, Helvetica Neue, Arial, sans-serif
- 全部无衬线体

## 禁止出现
- 版本说明、生产过程、元注释
- 来源标签（"HubToday"、"Hextra"等）
- 非原始链接（ai.hubtoday.app 链接绝对禁止）
- 深色背景 `#0F172A` 或任何需要深色背景才能看清的文字配色
- 缺少底部原文链接的新闻条目
- Outlook不兼容的CSS（渐变背景等）
