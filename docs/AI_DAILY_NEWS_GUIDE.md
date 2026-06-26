# AI 每日热点新闻系统说明

## 1. 项目概览

本项目每天自动完成 AI 新闻采集、LLM 编辑、HTML 日报生成、播客口播稿生成、
语音合成、质量校验、分阶段邮件发送及公网内容发布。

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
| 自动时间 | 每天北京时间 11:30 管理员检查发送，14:30 LLM 复审后自动上传文件并正式发送 |
| 手动运行 | 支持 |
| 邮件收件人 | `skill/references/recipients.json`，`admins` 用于上午，`all` 用于下午 |
| 新闻数量 | 每期 12 条 |
| LLM | OpenCode Go 模型自动降级链 |
| 播客 | 双人对话稿 + MP3 |
| 内容 API | GitHub Pages，HTTPS 公开访问 |
| 历史归档 | 自动保留 |
| 跨域访问 | 支持，`Access-Control-Allow-Origin: *` |

发送程序读取 `skill/references/send-email-config.json` 解析 `morning` / `afternoon`
phase，再从 `skill/references/recipients.json` 读取对应 audience。配置校验会在连接
SMTP 前完成。

---

## 3. 系统架构

```text
GitHub Actions 每日 11:30 触发管理员检查发送
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
        └── 发送管理员检查邮件
                └── skill/references/recipients.json

14:30 独立复审工作流
        │
        ├── 拉取当天公开成品
        ├── LLM 独立检查事实一致性、重复、可读性和播客质量
        ├── 再次执行确定性质量门禁
        ├── send_files=true 时上传重要文件到后端 API
        ├── 保存公开复审报告
        └── send_email=true 时发送至 recipients.json 中的 all
```

生成流水线与内容服务相互分离：

- 流水线负责计算、生成和校验。
- Pages 仅负责读取和分发已经生成的静态文件。
- Pages 中不保存 API Key、SMTP 密码或内部邮箱配置。

---

## 4. 每日工作流

上午工作流文件：

```text
.github/workflows/daily-news-test.yml
```

下午复审工作流文件：

```text
.github/workflows/daily-news-afternoon-review.yml
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
10. 验证收件人发送计划。
11. 更新 `gh-pages` 历史内容。
12. 根据运行参数发送对应 audience 邮件。
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

当前收件人配置：

```json
{
  "admins": [
    "yyc54321@126.com",
    "heyj17@lenovo.com"
  ],
  "all": [
    "yyc54321@126.com",
    "heyj17@lenovo.com",
    "heyujie1104@gmail.com"
  ]
}
```

相关文件：

```text
skill/references/recipients.json
skill/references/send-email-config.json
skill/references/send-file-config.json
skill/scripts/send_all.py
skill/references/smtp-config.md
scripts/upload_delivery_artifacts.py
```

邮件包含：

- 纯文本正文
- HTML 正文
- MP3 播客附件

自动定时任务默认发送邮件。手动运行时可通过 `send_email` 参数决定是否发送。

为降低 GitHub cron 偶发漏调度风险，两个时段均设置补偿触发：

- 上午：11:30、11:40、11:50、12:10。
- 下午：14:30、14:40、14:50、15:10。

每个阶段成功发送后会在 `gh-pages/state/deliveries/YYYY-MM-DD/` 写入幂等标记。
当天同阶段的后续补偿任务检测到标记后会立即跳过，因此不会因补偿 cron 重复发送。

下午复审的放行规则：

- 确定性门禁必须全部通过。
- LLM 不得判断存在明显事实矛盾。
- LLM 质量评分不得低于 50。
- 自动触发时 `send_files=true` 且 `send_email=true`。
- 手动触发时 `send_files` 控制是否上传后端，`send_email` 控制是否发全员邮件。
- 如果同一次运行中两个开关都为 true，后端上传必须成功后才会发送全员邮件。
- 文风或模板化表达等非致命问题会记录到公开复审报告，但不会单独阻止发送。

### 发送前后端上传

下午流程在 `send_files=true` 时会调用：

```bash
python3 scripts/upload_delivery_artifacts.py \
  --date YYYY-MM-DD
```

默认 endpoint：

```text
http://8.137.39.142:8000/mock/receive
```

后续地址、字段映射或 artifact 目录变化时，不需要改代码，修改：

```text
skill/references/send-file-config.json
```

临时覆盖 endpoint 时，可配置 GitHub Actions Variable 或 Secret：

```text
AI_DAILY_PRE_SEND_API_URL
```

上传文件来自 `review-dist/`：

| 字段 | 文件 |
|---|---|
| `jsons` | `articles-YYYY-MM-DD.json`、`podcast-script-YYYY-MM-DD.json`、`quality-review-YYYY-MM-DD.json` |
| `htmls` | `daily-news-YYYY-MM-DD.html` |
| `docs` | `podcast-script-YYYY-MM-DD.txt`、`daily-news-podcast-YYYY-MM-DD.mp3` |

上传失败会使 workflow 失败；如果本次同时 `send_email=true`，会阻断 `--phase afternoon` 全员发送。

### 安全限制

`send_all.py` 从 `skill/references/send-email-config.json` 读取 phase 配置，再从
`skill/references/recipients.json` 读取指定 audience，并验证：

1. 配置必须是非空 JSON 对象。
2. 每个 audience 必须是非空 JSON 字符串数组。
3. 每一项必须是合法邮箱地址，且同一 audience 内不得重复。
4. 不允许恢复或读取历史全员名单。

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

下午复审 workflow 另有：

```text
send_files=true   上传 review-dist 中的重要文件到后端 API
send_files=false  不上传文件，便于只测试复审或邮件路径
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
| `AI_DAILY_PRE_SEND_API_URL` | 可选，临时覆盖 `send-file-config.json` 中的上传地址 |

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
4. 日志是否出现 `Audience: admins` 或 `Audience: all` 以及 `成功: N / N`。

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
