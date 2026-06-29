# AI 每日热点新闻 — 完整复现手册

完整的系统架构、接口、运维与故障排查说明见：
[docs/AI_DAILY_NEWS_GUIDE.md](docs/AI_DAILY_NEWS_GUIDE.md)。

## 本地仓库部署

```bash
chmod +x scripts/*.sh
./scripts/deploy_local.sh
./scripts/smoke_test.sh
```

默认将 `skill/` 以符号链接部署到
`${CODEX_HOME:-$HOME/.codex}/skills/ai-daily-news`。本地修改仓库后无需重复复制。

## GitHub Actions 测试工作流

`.github/workflows/daily-news-test.yml` 支持：

- 每天北京时间 11:30 自动运行
- GitHub 页面手动触发
- 生成 HTML、测试播客和 JSON 报告
- 执行 HTML 质量门禁
- 发送器 dry-run 验证
- 可选真实发送；发送 phase、audience 和标题后缀由 `skill/references/send-email-config.json` 配置
- 上传 14 天可下载的运行产物

工作流会优先采集当天日报；如果当天页面尚未发布，则最多向前回退 3 天，并在
JSON 运行报告及邮件页脚记录实际内容日期。

采集完成后使用 OpenCode Go 完成新闻筛选、事件去重、分类、正文改写、AI 锐评和
播客对话稿生成。默认模型降级链为
`deepseek-v4-flash → deepseek-v4-pro → mimo-v2.5`；每个调用都会在运行报告中记录
实际使用的模型。若全部模型失败或结构化结果未通过规则校验，流水线会失败，不会
退回固定模板生成。

## 一、系统概览

每天自动采集 AI 行业新闻，生成 HTML 邮件 + 双人对话播客，分发给团队。

```
11:30  生成 + review 发 recipients.json 中的 admins
14:30  质量复检 → send_files 文件上传 → send_email 发送 recipients.json 中的 all
```

---

## 二、API / Key / 账号

### SMTP 发信（163 邮箱）
| 项 | 值 |
|----|-----|
| 邮箱 | `only_for_aics_tic@163.com` |
| 授权码 | `FZbuF344Ef7zDKLr` |
| 服务器 | `smtp.163.com:465`（SSL） |

⚠️ 163 有限流：每封间隔 8-10 秒，每 10 封暂停 30 秒。带大附件时更容易触发。

### 播客 TTS（硅基流动 SiliconFlow）
| 项 | 值 |
|----|-----|
| API Key | `sk-xlh…vzmm`（来自 openclaw.json embeddings 配置）|
| Endpoint | `POST https://api.siliconflow.cn/v1/audio/speech` |
| Model | `fnlp/MOSS-TTSD-v0.5` |
| 老陈(S1) reference | `moss-ttsd/references/voice_laochen_s1.wav` |
| 小满(S2) reference | `moss-ttsd/references/voice_anna_s2.mp3` |
| 响应格式 | `response_format: "mp3"` |

⚠️ 通过 SiliconFlow `/audio/speech` 调用 MOSS-TTSD，必须只使用仓库 `moss-ttsd/references/` 中的两个参考音频。

### 播客单独测试

用已有 `articles-YYYY-MM-DD.json` 或 `news-data-YYYY-MM-DD.json` 只重新生成播客脚本和 MP3，不发布、不发送：

```bash
python scripts/generate_podcast_only.py \
  --date 2026-06-26 \
  --articles review-dist/articles-2026-06-26.json \
  --output-dir tmp/podcast-test
```

只测试对话文本、不调用 TTS：

```bash
python scripts/generate_podcast_only.py \
  --date 2026-06-26 \
  --articles review-dist/articles-2026-06-26.json \
  --output-dir tmp/podcast-test \
  --skip-audio
```

`--articles` 也支持传入 `https://.../articles.json` URL。

生成音频时建议传入两个 reference audio 的准确台词，或配置同名环境变量
`MOSS_TTS_S1_REFERENCE_TEXT`、`MOSS_TTS_S2_REFERENCE_TEXT`：

```bash
python scripts/generate_podcast_only.py \
  --date 2026-06-26 \
  --articles review-dist/articles-2026-06-26.json \
  --output-dir tmp/podcast-test \
  --s1-reference-text "voice_laochen_s1.wav 的准确台词" \
  --s2-reference-text "voice_anna_s2.mp3 的准确台词"
```

### 邮件收件人

**管理员检查收件人（11:30，`admins`）**：
- `yyc54321@126.com`
- `heyj17@lenovo.com`

**下午正式收件人（14:30，`all`）**：
- `yyc54321@126.com`
- `heyj17@lenovo.com`
- `heyujie1104@gmail.com`
- 发送器从 `skill/references/recipients.json` 读取并校验邮箱格式。

发送阶段配置在 `skill/references/send-email-config.json`：

- `morning` → `admins`
- `afternoon` → `all`
- 邮件标题后缀、发送间隔、批次暂停和重试参数也在这里维护。

---

## 三、每日时间线

```
11:30 GMT+8  ai-daily-news cron 触发
           ├─ Step 1: 预检（~1 min）
           ├─ Step 2: 数据采集 + 链接验证（~5 min）
           ├─ Step 3: HTML 生成 + 质量门禁（~5 min）
           ├─ Step 3.5: 播客合成（~5-8 min）
           ├─ Step 4: 发 review 邮件给 recipients.json 中的 admins
           └─ Step 5: 留样 + 日志
           
11:30-14:30  管理员（BIL）可审核 review 邮件，有问题可取消

14:30 GMT+8  check-and-distribute cron 触发
           ├─ send_files=true → 文件上传
           └─ send_email=true → 发送 recipients.json 中的 all
```

---

## 四、数据来源

### 主源：hex2077.dev 日报归档
```
https://hex2077.dev/docs/YYYY-MM/YYYY-MM-DD/
```
- 静态文档，web_fetch 可抓
- 每条新闻自带原文外链
- 约 20-30 条候选

### 备用源
- 量子位 `https://www.qbitai.com/` — web_fetch 经常 403
- 36kr AI频道 `https://36kr.com/information/AI` — 抽取不稳定
- 机器之心 `https://www.jiqizhixin.com/`

### 禁止的来源
- ❌ AIbase — 链接不能作为原文 URL（需提取原始来源）
- ❌ HubToday — 已迁移至 hex2077，不再使用
- ❌ 微信验证码页 — 含 `wappoc_appmsgcaptcha` 或 `mp.weixin.qq.com/mp/wappoc` 直接淘汰

### 链接验证规则
- 墙外域名直接信任跳过验证：`x.com, twitter.com, reddit.com, techcrunch.com, bloomberg.com, nytimes.com, the-decoder.com, newshacker.me, huggingface.co, github.com`
- 墙内域名必须：HEAD 检查 → 标题匹配 ≥ 30% → 正文 ≥ 100 字

---

## 五、质量门禁（⚠️ 一项不过就 BLOCKED）

运行 `validate_html_quality.py --date YYYY-MM-DD`，必须全部 PASS：

| # | 门禁 | 说明 |
|---|------|------|
| 1 | HTML 存在且 ≥ 15KB | 文件完整性 |
| 2 | 聚合源域名计数 = 0 | hubtoday/hex2077/hextra/aibase.com 均为 0 |
| 3 | &#x 实体 = 0 | 中文不能有 HTML 实体编码 |
| 4 | 聚合源短语 = 0 | 不能出现"HubToday 归档称"等句式 |
| 5 | 唯一链接数 ≥ 8 | 且不能是站点首页根路径 |
| 6 | 正文块 ≥ 8（去标签 ≥ 80 字） | 兼容 div/p/td 标签 |
| 7 | 栏目顺序符合规范 | 今日焦点 > 产品发布 > 行业动态 > 前沿研究 > ... |
| 8 | 正文字数 ≥ 120 字/条 | 禁止空洞凑字数 |

---

## 六、HTML 格式规范

### 模板参考
`skill/templates/v4-2026-03-18.html`

### 结构
- 700px 宽邮件兼容表格布局
- 蓝色标题栏（#3b82f6）
- 今日摘要 → 各栏目 → 页脚
- 每条新闻卡片：标题链接 → `<p data-role="news-body">` → AI锐评（橙色边框） → 原文链接

### AI 锐评要求
- 犀利、主观、有观点，1-2 句
- 可以调侃、批评、赞叹
- 禁止温和废话

### 栏目顺序（不可乱序）
1. 🔥 今日焦点（固定 1 条）
2. 🚀 产品发布
3. 💼 行业动态
4. 📜 政策 & 监管
5. 💡 前沿研究
6. 🔓 开源热榜
7. 🤖 Agent & 工具
8. 💰 商业 & 融资
9. 🇨🇳 国内 AI

---

## 七、播客规范

### 脚本要求
- 双人对话：S1 老陈（男声，资深 AI 视角）+ S2 小满（女声，产品视角）
- 6-7 条精选新闻，不要全报
- 禁止机械播报（"第一条新闻是…"），必须用自然对话
- 每条 8-12 句，包含观点碰撞
- 目标 5-10 分钟

### 合成方式
- 单次调用 SiliconFlow MOSS-TTSD 双人对话合成
- 输入使用 `[S1]... [S2]...` 对话标签，并传入两个本地 reference audio
- 检查总大小，超过 8MB 降码率到 48k

---

## 八、常见踩坑点

| # | 坑 | 解决方案 |
|---|-----|---------|
| 1 | **aibase.com 链接不能直接使用** | 必须提取原文来源，或用 Exa 搜索替代 URL。验证脚本会计数所有 aibase.com 出现 |
| 2 | **web_search (Brave) 不可用** | 用 `mcporter call exa.web_search_exa` 替代。注意 Exa 免费额度有限 |
| 3 | **hex2077 静态页可能 404** | 降级到量子位 / 36kr |
| 4 | **微信文章链接跳验证码** | 含 `wappoc_appmsgcaptcha` 的直接淘汰 |
| 5 | **中文写成 &#x 实体** | 写文件必须 `encoding="utf-8"`，写完立即验证 |
| 6 | **Copilot token 过期** | 去掉 cron 的 model override，用默认模型 |
| 7 | **MOSI API key 失效** | 改用 SiliconFlow CosyVoice |
| 8 | **send-all 脚本挂起无输出** | SMTP 连接断开后等待重连，给足超时时间（≥15 min） |
| 9 | **栏目顺序漂移** | 严格按规范顺序排列，缺栏目跳过但不乱序 |
| 10 | **播客超过 8MB** | 自动降码率到 48k |
| 11 | **/tmp 空间不足** | 预检时检查，清理旧文件 |

---

## 九、关键文件索引

```
skill/
├── SKILL.md                    # 主流程定义
├── templates/
│   └── v4-2026-03-18.html      # HTML 邮件模板
├── references/
│   ├── fault-prevention.md     # 禁止规则 + 预检 + 自检清单
│   ├── content-rules.md        # 栏目结构、正文要求、锐评、去重
│   ├── html-design.md          # 配色、字体、结构
│   ├── smtp-config.md          # SMTP 配置
│   ├── recipients.json         # 分阶段收件人 JSON（admins/all）
│   ├── send-email-config.json  # 邮件发送 phase/audience/节流配置
│   ├── send-file-config.json   # 文件上传配置
│   ├── recent-issues-state.md  # 跨天去重状态
│   └── send-log.md             # 发送日志
├── scripts/
│   ├── check_and_distribute.py # 14:30 质量检查 + send-all
│   ├── validate_html_quality.py # HTML 质量校验
│   ├── smtp_probe.py           # SMTP 预检
│   └── send_all.py             # 受控邮件发送器
├── samples/                    # HTML 留样归档
├── logs/                       # 每日执行日志
└── moss-ttsd/                  # 旧版 TTS 脚本（参考用）
    └── scripts/mosi_dialogue.sh
```

仓库根目录 `scripts/upload_delivery_artifacts.py` 负责文件上传。

---

## 十、Cron 任务配置

### 任务 1: ai-daily-news
- **时间**：每天 11:30 GMT+8
- **Session**：isolated
- **模型**：无覆盖（使用默认）
- **操作**：读取 SKILL.md 执行完整流程
- **分发**：review 邮件 → `skill/references/recipients.json` 的 `admins`

### 任务 2: check-and-distribute
- **时间**：每天 14:30 GMT+8
- **Session**：isolated
- **操作**：运行 `check_and_distribute.py`，通过后发送 `recipients.json` 的 `all`
- **send_files**：控制是否执行文件上传
- **send_email**：控制是否调用 `send_all.py --phase afternoon` 发全员邮件
- **自动触发**：`send_files=true` 且 `send_email=true`
- **Auto-send**：无人取消则自动执行

### 文件上传

下午流程会按 `send_files` 开关把 `review-dist/` 中配置的文件上传到后端 API。默认地址：

```text
http://8.137.39.142:8011/mock/receive
```

默认认证配置同样在 `send-file-config.json`：

```text
Authorization: Bearer tsd-tic
```

后续 IP、路径、认证、上传文件或 artifact 目录变化时，优先改：

```text
skill/references/send-file-config.json
```

临时调试时也可以用 GitHub Actions Variable 或 Secret 覆盖 endpoint：

```text
AI_DAILY_PRE_SEND_API_URL
```

临时覆盖认证 token：

```text
AI_DAILY_PRE_SEND_API_TOKEN
```

当前只上传两个文件：

- `jsons`：`articles-YYYY-MM-DD.json`
- `docs`：`daily-news-podcast-YYYY-MM-DD.mp3`

自动触发时 `send_files` 和 `send_email` 都视为 true。手动触发时可单独测试上传或邮件；如果两个都开启，上传步骤位于邮件发送之前，上传失败会阻断后续邮件发送。

---

## 十一、环境依赖

- Python 3 （命令用 `python3`，没有 `python`）
- ffmpeg ≥ 6.x
- node ≥ 22（mcporter / SiliconFlow API 调用）
- curl
- bash

---

## 十二、手动触发

在 Discord #新闻 频道说 "手动运行" 即可，可加参数如：
- "手动运行，只发管理员"
- "手动运行，不要转发"
- "手动运行，全程（含播客）"

---

## 十三、内容 API

每日任务成功后会同步更新 GitHub Pages 静态内容服务：

- `/api/latest.json`
- `/feed.json`
- `/api/issues/YYYY-MM-DD/index.json`
- `/api/issues/YYYY-MM-DD/articles.json`
- `/api/issues/YYYY-MM-DD/podcast-script.json`
- `/html/YYYY-MM-DD.html`
- `/audio/YYYY-MM-DD.mp3`

服务只发布日报内容，不包含邮箱、Secrets 或内部运行配置。
