# AI 每日热点新闻系统说明

## 1. 项目概览

本项目每天自动完成 AI 新闻采集、LLM 编辑、HTML 日报生成、播客口播稿生成、
语音合成、质量校验、测试邮件发送及公网内容发布。

当前运行环境不依赖 VPS：

- GitHub Actions：执行每日工作流
- GitHub Pages：提供 24 小时可访问的静态内容 API
- OpenCode Go：提供新闻编辑及播客脚本生成模型
- SiliconFlow：提供双人播客语音合成
- 163 SMTP：发送 HTML 日报及 MP3 附件

源码仓库：

<https://github.com/dedarek/ai-daily-news-workflow>

内容服务：

<https://dedarek.github.io/ai-daily-news-workflow/>

---

## 2. 当前运行状态

| 项目 | 当前状态 |
|---|---|
| 工作流 | 已部署至 GitHub Actions |
| 自动时间 | 每天北京时间 11:30 |
| 手动运行 | 支持 |
| 邮件收件人 | 仅 `yyc54321@126.com` |
| 新闻数量 | 每期 12 条 |
| LLM | OpenCode Go 模型自动降级链 |
| 播客 | 双人对话稿 + MP3 |
| 内容 API | GitHub Pages，HTTPS 公开访问 |
| 历史归档 | 自动保留 |
| 跨域访问 | 支持，`Access-Control-Allow-Origin: *` |

发送程序包含收件人硬限制。如果配置文件出现第二个邮箱，程序会在连接 SMTP
之前直接终止。

---

## 3. 系统架构

```text
GitHub Actions 每日 11:30 触发
        │
        ├── 抓取最新可用 AI 日报源
        │
        ├── 提取标题、摘要和真实文章链接
        │
        ├── OpenCode Go LLM
        │   ├── 选题与去重
        │   ├── 栏目分类
        │   ├── 正文改写
        │   ├── AI 锐评
        │   └── 双人播客脚本
        │
        ├── SiliconFlow TTS 合成 MP3
        │
        ├── HTML 与音频质量门禁
        │
        ├── 发布 GitHub Pages 内容 API
        │
        └── 发送测试邮件
                └── yyc54321@126.com
```

生成流水线与内容服务相互分离：

- 流水线负责计算、生成和校验。
- Pages 仅负责读取和分发已经生成的静态文件。
- Pages 中不保存 API Key、SMTP 密码或内部邮箱配置。

---

## 4. 每日工作流

工作流文件：

```text
.github/workflows/daily-news-test.yml
```

执行顺序：

1. 检出私有源码仓库。
2. 安装 Python 3.12 和 FFmpeg。
3. 获取北京时间日期。
4. 运行源码烟雾测试。
5. 采集最新可用新闻。
6. 调用 LLM 生成结构化内容。
7. 生成 HTML 日报和播客口播稿。
8. 调用 SiliconFlow 合成 MP3。
9. 执行 HTML、链接、栏目及音频质量门禁。
10. 验证唯一收件人发送计划。
11. 更新 `gh-pages` 历史内容。
12. 根据运行参数发送测试邮件。
13. 上传 GitHub Actions 运行产物。

### 数据日期回退

工作流优先抓取当天数据。如果当天内容尚未发布，会依次尝试前一天，最多向前
回退 3 天。

以下两个日期会分别记录：

- `issue_date`：本期日报发布日期。
- `content_date`：实际使用的新闻源日期。

---

## 5. LLM 配置

Provider：

```text
opencode-go
```

Base URL：

```text
https://opencode.ai/zen/go/v1
```

接口：

```text
POST /chat/completions
```

默认模型降级链：

```text
deepseek-v4-flash
→ deepseek-v4-pro
→ mimo-v2.5
```

单个模型遇到以下情况会自动重试或切换：

- HTTP 429
- HTTP 500、502、503、504
- JSON 格式损坏
- 模型输出未正常结束
- 结构化结果不符合约束

工作流不设置 `max_tokens` 上限。

每期共执行 5 个编辑调用：

1. 选题、去重及分类。
2. 第一批 4 条正文。
3. 第二批 4 条正文。
4. 第三批 4 条正文。
5. 播客对话稿。

运行报告会记录每一步实际使用的模型与 Token 统计。

---

## 6. 播客系统

播客角色：

| 标识 | 姓名 | 定位 |
|---|---|---|
| S1 | 老陈 | 资深 AI 从业者 |
| S2 | 小满 | 产品与应用视角 |

TTS 配置：

```text
Provider: SiliconFlow
Model: FunAudioLLM/CosyVoice2-0.5B
S1 Voice: alex
S2 Voice: anna
Format: MP3
Bitrate: 64k
```

如果 SiliconFlow 请求失败，当前流程会生成备用测试音频，并在运行报告中将
`tts_mode` 标记为 `fallback-sample`。

正常实时音频标记为：

```json
{
  "tts_mode": "siliconflow-live"
}
```

---

## 7. 邮件发送

当前唯一允许的收件人：

```text
yyc54321@126.com
```

相关文件：

```text
skill/references/recipients.md
skill/scripts/send_all.py
skill/references/smtp-config.md
```

邮件包含：

- 纯文本正文
- HTML 正文
- MP3 播客附件

自动定时任务默认发送邮件。手动运行时可通过 `send_email` 参数决定是否发送。

### 安全限制

`send_all.py` 同时验证：

1. 配置中只能出现一个邮箱。
2. 邮箱必须严格等于 `yyc54321@126.com`。
3. 不允许恢复或读取历史全员名单。

---

## 8. 公网内容 API

服务根地址：

```text
https://dedarek.github.io/ai-daily-news-workflow
```

### 最新一期

```http
GET /api/latest.json
```

完整地址：

<https://dedarek.github.io/ai-daily-news-workflow/api/latest.json>

示例结构：

```json
{
  "schema_version": 1,
  "issue_date": "2026-06-25",
  "content_date": "2026-06-25",
  "article_count": 12,
  "podcast_turns": 16,
  "tts_mode": "siliconflow-live",
  "articles_url": "https://.../articles.json",
  "podcast_script_url": "https://.../podcast-script.json",
  "html_url": "https://.../2026-06-25.html",
  "audio_url": "https://.../2026-06-25.mp3"
}
```

### 历史列表

```http
GET /feed.json
```

<https://dedarek.github.io/ai-daily-news-workflow/feed.json>

### 指定日期元数据

```http
GET /api/issues/YYYY-MM-DD/index.json
```

### 新闻内容

```http
GET /api/issues/YYYY-MM-DD/articles.json
```

每条新闻包含：

```json
{
  "title": "新闻标题",
  "summary": "LLM 编辑后的正文",
  "url": "原始文章链接",
  "section": "栏目",
  "review": "AI 锐评"
}
```

### 播客口播稿

```http
GET /api/issues/YYYY-MM-DD/podcast-script.json
```

示例：

```json
{
  "issue_date": "2026-06-25",
  "speakers": {
    "S1": {
      "name": "老陈",
      "role": "资深AI从业者"
    },
    "S2": {
      "name": "小满",
      "role": "产品与应用视角"
    }
  },
  "dialogue": [
    {
      "speaker": "S1",
      "text": "..."
    }
  ]
}
```

### HTML 日报

```http
GET /html/YYYY-MM-DD.html
```

### MP3 播客

```http
GET /audio/YYYY-MM-DD.mp3
```

音频支持 HTTP Range 请求，可用于浏览器及播放器流式播放。

---

## 9. 调用示例

### JavaScript

```javascript
const base = "https://dedarek.github.io/ai-daily-news-workflow";

const latest = await fetch(`${base}/api/latest.json`).then(r => r.json());
const articles = await fetch(latest.articles_url).then(r => r.json());
const script = await fetch(latest.podcast_script_url).then(r => r.json());

console.log(latest.issue_date);
console.log(articles[0].title);
console.log(script.dialogue[0]);
```

### Python

```python
import requests

base = "https://dedarek.github.io/ai-daily-news-workflow"
latest = requests.get(f"{base}/api/latest.json", timeout=20).json()
articles = requests.get(latest["articles_url"], timeout=20).json()

print(latest["issue_date"])
print(articles[0]["title"])
```

### curl

```bash
curl -fsSL \
  https://dedarek.github.io/ai-daily-news-workflow/api/latest.json
```

---

## 10. 手动运行

进入 GitHub 仓库：

```text
Actions
→ AI Daily News Test
→ Run workflow
```

参数：

```text
send_email=true   生成、发布并发送邮件
send_email=false  只生成和发布，不发送邮件
```

CLI 示例：

```bash
gh workflow run daily-news-test.yml \
  --repo dedarek/ai-daily-news-workflow \
  -f send_email=false
```

查看运行：

```bash
gh run list \
  --repo dedarek/ai-daily-news-workflow \
  --workflow daily-news-test.yml
```

---

## 11. GitHub Secrets

仓库当前依赖以下 Secrets：

| Secret | 用途 |
|---|---|
| `OPENCODE_GO_API_KEY` | LLM 调用 |
| `SILICONFLOW_API_KEY` | 播客语音合成 |
| `AI_DAILY_SMTP_USER` | SMTP 发件账号 |
| `AI_DAILY_SMTP_PASSWORD` | SMTP 授权码 |

Secret 只注入 GitHub Runner，不会发布到 GitHub Pages。

---

## 12. 质量门禁

日报发送及发布前会检查：

- HTML 大于 15KB
- MP3 在 1,000,000 至 8MiB 之间
- 至少 8 条新闻正文
- 至少 8 个唯一原文链接
- 不允许网站首页链接
- 不允许聚合源域名或名称进入正文
- 不允许微信验证码页面
- 新闻正文必须使用 `<p data-role="news-body">`
- 栏目顺序必须稳定
- 中文不能被写成 `&#xXXXX;` 实体

任一门禁失败都会阻止邮件发送和内容发布。

---

## 13. 公网服务可用性

GitHub Pages 通过以下端口提供服务：

```text
HTTPS: 443
HTTP: 80，自动跳转至 HTTPS
```

已验证：

- HTTPS 443 TCP 连通
- TLS 证书验证通过
- HTTP 301 跳转 HTTPS
- JSON、HTML、MP3 返回 HTTP 200
- MP3 支持 Range 请求
- API 返回 `Access-Control-Allow-Origin: *`

该服务不需要自建 VPS，也没有需要维护的应用进程或监听端口。

可用性依赖 GitHub Pages 平台，不提供项目自有 SLA。

---

## 14. 常见故障

### LLM 网关 502

系统会自动重试，并按以下顺序切换模型：

```text
Flash → Pro → MiMo V2.5
```

### LLM 返回损坏 JSON

同一模型最多重新生成 3 次，之后切换下一个模型。

### 当天新闻源未发布

自动向前回退，最多尝试 3 天。

### TTS 失败

生成备用音频，报告中的 `tts_mode` 会显示为 `fallback-sample`。

### Pages 尚未更新

GitHub Pages 默认存在约 10 分钟缓存：

```http
Cache-Control: max-age=600
```

可以查看 `gh-pages` 分支是否已经产生新提交。

### 邮件没有发送

检查：

1. `send_email` 是否为 `true`。
2. 质量门禁是否通过。
3. SMTP Secrets 是否存在。
4. 日志是否出现 `成功: 1 / 1`。

---

## 15. 后续升级方向

当前 GitHub Pages 方案适合早期内容服务。出现以下需求后可迁移到 Cloudflare
Workers + R2：

- API Token 鉴权
- 动态搜索和筛选
- 用户订阅管理
- 自定义域名
- 更大的音频存储
- 更严格的 SLA 和监控
- 服务端统计与调用限流

现有 API 路径和 JSON Schema 可以保持不变，调用方无需跟随底层托管平台迁移。
