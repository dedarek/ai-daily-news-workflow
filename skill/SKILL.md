---
name: ai-daily-news
description: Generate, validate, review, and distribute a Chinese daily AI news digest with HTML email and a two-speaker podcast. Use when Codex is asked to run, test, maintain, or troubleshoot the AI daily-news workflow, its quality gates, scheduled review email, podcast synthesis, or recipient distribution.
---

# AI Daily News — Skill 定义

- **产品名称**：每日AI热点新闻（试运营）
- **受众**：公司内部技术团队
- **发送渠道**：邮件（播客附件）+ 飞书消息（暂停）+ 飞书文档备份（暂停）
- **发送时间**：每天 11:30 北京时间发管理员检查邮件，14:30 北京时间复审通过后发正式邮件（定时自动 + 支持手动触发）
- **每期条数**：12-15 条（最低 5 条，少于 5 条暂停发送） | **调性**：轻松可读
- **当前模式**：分阶段发送，邮件 phase 配置源为 `references/send-email-config.json`，收件人配置源为 `references/recipients.json`

**⛔ 严格遵循 `references/fault-prevention.md` 中的所有约束规则。**

---

## 执行步骤

### Step 1: 预检
读取 `references/fault-prevention.md`，执行全部预检项。任何一项失败立即终止。

- **SMTP 预检强制要求**：不要只看 `openssl s_client` 的退出码。统一使用 `python3 scripts/smtp_probe.py --json-out /tmp/ai-daily-news-precheck-YYYY-MM-DD.json`，按握手内容（`CONNECTION ESTABLISHED` / `Protocol version:` / `Verification: OK` / `220` / `221`）判定是否成功。

### Step 2: 数据采集 + 链接实检
**⛔ 禁止用 sessions_spawn，用 exec 后台执行脚本 + process poll 等待结果**

- **执行方式**：将完整的采集+链接实检逻辑写成一个 python/bash 脚本，用 `exec` 后台运行（设置 `background: true` 或 `yieldMs`），然后用 `process poll` 等待完成，最后 `read` 结果文件
- **⛔⛔⛔ 严禁逐条 exec**：绝对禁止对每个 URL 单独调用 exec 做 curl/HEAD 检查。所有 URL 验证必须在一个脚本内批量完成。逐条 exec 会在 60 步内撑爆 context window 导致任务失败。正确做法：写一个 Python 脚本，在脚本内用 requests/urllib 批量验证所有 URL，一次性输出 JSON 结果文件
- **输入**：执行日期（`YYYY-MM-DD`）
- **任务**：
  1. 用 **web_fetch** 抓取以下数据源，提取新闻标题、摘要和真实文章链接：
     - **主源1：量子位** `https://www.qbitai.com/` — 提取当日文章链接（格式：`/2026/05/xxxxx.html`）
     - **主源2：36kr AI频道** `https://36kr.com/information/AI` — 提取文章链接（格式：`/p/xxxxx`）
     - 备用：机器之心 `https://www.jiqizhixin.com/`
     ⚠️ **AIbase 已废弃作为数据源**（文章页不提供原文外链）
     - **首选：hex2077.dev 日报归档** `https://hex2077.dev/docs/YYYY-MM/YYYY-MM-DD/`（静态文档，web_fetch 可抓，每条新闻自带原文外链）
     - 备用：量子位 `https://www.qbitai.com/`、36kr `https://36kr.com/information/AI`
     **⛔ AIbase 链接禁止作为原文链接**：必须进入每条 AIbase 文章页面，提取文章底部或正文中的原始来源链接（官方博客/GitHub/The Verge/TechCrunch 等），用原始链接作为邮件中的"阅读原文"链接。无法找到原始链接的条目直接淘汰。
     **⛔ AIbase 同主题去重**：AIbase 经常对同一事件发多篇报道，采集后必须按核心事件去重，相同事件只保留信息量最大的一条。
     ⚠️ **HubToday 已迁移至 hex2077.dev（SPA 渲染，web_fetch 无法获取列表），不再作为数据源**
     AIbase 抓取失败时，备用源：web search 搜索当日 AI 新闻（关键词：AI news YYYY-MM-DD）
     **⛔ 禁止用 browser tool 的 snapshot，内容太大撑爆上下文；禁止用 curl，SPA 页面无法渲染**
  2. 如果 web_fetch 结果中某些新闻没有链接，用 web search 搜索该新闻标题获取真实文章 URL（最多 2 轮）
  3. 所有后续验证逻辑（URL 检查、标题匹配、正文长度）全部在脚本内完成，禁止通过 exec 逐条调用
- **链接实检（必须执行，但跳过墙外域名）**：对每个候选 URL 验证：
  - ⚠️ **以下域名直接信任，跳过 HEAD/标题/正文验证**（服务器无法访问）：`x.com`、`twitter.com`、`reddit.com`、`techcrunch.com`、`bloomberg.com`、`nytimes.com` 及其他已知墙外站点。只要从 HubToday 页面提取到的链接域名匹配，视为 `url_valid: true`，不做进一步检查
  - 对**墙内可达域名**（如 `news.aibase.com`、`36kr.com` 等）：执行完整验证：
    1. HTTP HEAD 检查 → 404/403/超时直接淘汰
    2. 跟随重定向拿最终 URL
    3. 抓取页面 `<title>` 与新闻标题关键词重合度 ≥ 30%
    4. 正文有效性 ≥ 100 字，无「404/维护/验证码」等标记
    5. 不通过的直接淘汰，不补位
- **⛔ 禁止编造 URL**：如果某条新闻无法获取真实源链接，直接淘汰该条，绝对禁止推测或编造任何 URL
- **输出**：将结果写入文件 `/tmp/ai-daily-news-data-YYYY-MM-DD.json`（结构化 JSON，每条含 `title, summary, detail, source_url`，附验证结果）。**⛔ 不要把大段 JSON 写入聊天，只输出文件路径**
- **约束**：只采集，不生成 HTML，不发送。所有 URL 必须是经过验证的原始文章链接，禁止 hubtoday.app 链接
- **⛔ 数据清洗**：提取 title 和 summary 时，必须清理 HTML 标签残留（如 `(AI资讯)`、`(AIGC)` 等分类标签），括号内的分类标签不是新闻正文的一部分，必须移除
- **⛔ 微信验证码 URL 过滤**：任何包含 `wappoc_appmsgcaptcha`、`mp.weixin.qq.com/mp/wappoc` 的 URL 直接淘汰，这类链接是微信验证页面而非文章

### Step 3: 内容生成 + 验证（主 session）
1. 用 `read` 工具读取 `/tmp/ai-daily-news-data-YYYY-MM-DD.json`
2. 读取 `references/content-rules.md`（栏目结构、正文要求、锐评、去重）
3. 读取 `references/html-design.md`（配色、字体、HTML 结构）
4. 读取 `templates/v4-2026-03-18.html` 作为 HTML 模板参考（**必须参考模板结构和样式**）
5. 基于 JSON 生成 HTML 邮件 + 飞书纯文本
6. **去重**：与 `references/recent-issues-state.md` 比对
7. **自检**：按 `references/fault-prevention.md` 中的自检清单逐项检查
   - **新增强制文案门禁**：HTML 中大小写不敏感搜索 `hubtoday|hex2077|hextra|aibase` 必须为 0；如果正文出现“HubToday 归档称 / 当日页提到 / 援引聚合页”这类句子，必须重写
   - **必须执行自动校验脚本**：在 Skill 根目录运行 `python3 scripts/validate_html_quality.py --date YYYY-MM-DD`
   - 脚本非 0 退出即视为 HTML 不合格，禁止发送 review 邮件，必须回到正文重写后再验
8. 将 HTML 保存到 `/tmp/ai-daily-news-html-YYYY-MM-DD.html`，飞书文本保存到 `/tmp/ai-daily-news-feishu-YYYY-MM-DD.txt`
   **⛔ 写文件必须用 `open(path, "w", encoding="utf-8")` + 直接写中文字符串，禁止用 `ascii` 编码或任何会把中文转成 `&#xXXXX;` 实体的方式。写完后立即验证：`b"&#x" not in open(path,"rb").read()` 必须为 True，否则重写。**
9. **⛔ 强制字数自检（必须执行，不可跳过）**：
   - 用 exec 运行 Python 脚本解析 HTML，统计每条新闻 <p> 正文字数（排除链接行和 footer）
   - 找出所有正文字数 < 80 字的条目（约 3 句以下），输出 "FAIL: [标题] 只有 XX 字"
   - **如有任何 FAIL**：必须重写该条正文，补充到 >= 120 字（补充具体数据、技术细节、背景），更新 HTML，重复检查直到全部通过
   - ⛔ 禁止用"引发广泛关注"、"具有重要意义"等空洞词汇凑字数，必须是有信息量的真实内容
10. ⛔ **跳过浏览器截图预览**（避免上下文膨胀），直接进入分发

### Step 3.5: 播客合成
**⛔ 禁止用 sessions_spawn，用 exec 后台执行脚本 + process poll 等待结果**

- **执行方式**：
  1. 主 session 先读取 `/tmp/ai-daily-news-data-YYYY-MM-DD.json`，精选 5-7 条新闻，撰写对话脚本写入 `/tmp/ai-daily-news-podcast-YYYY-MM-DD.script`
  2. 将分段合成命令写成一个 shell 脚本，用 `exec` 后台运行（设置 `timeout: 1200` 即 20 分钟），用 `process poll` 等待完成
  3. 合成完成后读取 `/tmp/ai-daily-news-podcast-YYYY-MM-DD.status` 确认结果
  4. 超时或失败 → 重试一次 → 再失败放弃播客，记录错误，继续分发（邮件不带附件）

- **输入**：读取 `/tmp/ai-daily-news-data-YYYY-MM-DD.json` 中的新闻数据

- **任务**：
  1. **撰写双人对话脚本**（⚠️ 这是影响播客质量的关键步骤，必须认真写）：
     - 两人设定：S1 = 老陈（男声，资深AI从业者视角），S2 = 小满（女声，产品/应用视角）
     - **调性：自然对话播客**，像真正的播客节目——两人真的在聊、在思考、有分歧有共鸣
     - **从新闻中精选 5-7 条最值得深聊的**，不要全播报，宁精勿滥
     - **⛔ 绝对禁止机械播报格式**。禁止"第一条新闻是…""接下来我们聊聊…"这种流水账
     - **用自然话题过渡**：用"说到这个我想起…""对了还有个事…""你看到那个…没""说完硬件说软件…"这类口语化过渡
     - **每条新闻 8-12 句对话**，包含：
       - 一人抛出事件（口语化引入，不是念标题）
       - 另一人反应+补充观点
       - 深入分析（技术细节、行业影响、背后原因）
       - 自然过渡到下一条
     - **加入主观判断和个人观点**（"我觉得这个…""你不觉得这个时机太巧了吗…"）
     - **适当联想串联**相关新闻（"说完技术说监管…"）
     - 总时长目标：8-12 分钟对话内容
     - 文本格式：每行以 `[S1]` 或 `[S2]` 开头。每段讨论（一个话题）≤ 40 行，段与段之间空一行分隔

  2. **合成音频**（使用 MOSI 官方 API mosi_dialogue.sh）：
     - 脚本路径：`~/.openclaw/workspace-research/skills/moss-ttsd/scripts/mosi_dialogue.sh`
     - ⛔ **必须显式 export 环境变量**：`export MOSI_TTS_API_KEY="sk-726c3a87ccf9dd6f845436d827b4c9f5c39e9c3ff630ff0b"`（cron session 不加载 .bashrc）
     - S1（老陈）：`--voice1 2040784925577187328`
     - S2（小满）：`--voice2 2001910895478837248`（甜美开朗女声）
     - **⛔ 因为文本较长，必须分段合成**（每段 ≤ 15 行对话文本），逐段调用 mosi_dialogue.sh
     - 每段输出：`/tmp/ai-daily-news-podcast-YYYY-MM-DD-part{N}.wav`
     - ffmpeg concat 拼接所有段为完整 WAV：`ffmpeg -f concat -safe 0 -i filelist.txt -c copy /tmp/ai-daily-news-podcast-YYYY-MM-DD.wav`
     - 转 MP3（**必须限制码率，避免触发 163 限流**）：
       ```
       ffmpeg -i /tmp/ai-daily-news-podcast-YYYY-MM-DD.wav -codec:a libmp3lame -b:a 64k /tmp/ai-daily-news-podcast-YYYY-MM-DD.mp3
       ```
       ⚠️ **强制使用 64k 码率**（语音内容 64k 完全够用，比 128k 节省一半体积）
       转码后检查文件大小，**如果超过 8MB，改用 48k 再转一次**：
       ```
       SIZE=$(stat -c%s /tmp/ai-daily-news-podcast-YYYY-MM-DD.mp3); if [ $SIZE -gt 8388608 ]; then ffmpeg -y -i /tmp/ai-daily-news-podcast-YYYY-MM-DD.wav -codec:a libmp3lame -b:a 48k /tmp/ai-daily-news-podcast-YYYY-MM-DD.mp3; fi
       ```
     - 最终输出：`/tmp/ai-daily-news-podcast-YYYY-MM-DD.mp3`

  3. **输出**：音频文件路径和时长写入 `/tmp/ai-daily-news-podcast-YYYY-MM-DD.status`（成功写路径，失败写错误信息）

### Step 4: 分发
**⛔ 禁止用 sessions_spawn，在主 session 内用 exec + message 工具直接执行**

- **输入**：读取 `/tmp/ai-daily-news-html-YYYY-MM-DD.html` + 播客音频路径（如有）
- **任务**：
  - 📧 邮件：
    - **收件人唯一来源**：`references/recipients.json`
    - **发送 phase 配置来源**：`references/send-email-config.json`
    - **上午管理员检查**：`python3 scripts/send_all.py --date YYYY-MM-DD --phase morning`
    - **下午正式分发**：`python3 scripts/send_all.py --date YYYY-MM-DD --phase afternoon`
    - 发送前可加 `--dry-run` 验证指定 phase 的收件人配置、HTML 与 MP3 输入。
    - ⛔ 禁止在 `SKILL.md`、临时脚本、prompt 或 workflow 中另写收件人名单或 phase 映射；新增或删除收件人只能改 `references/recipients.json`，调整阶段策略只能改 `references/send-email-config.json`。
    - 14:30 质量复检后如需发送，仍调用同一个发送器并使用 `--phase afternoon`。
    - 读取 `references/smtp-config.md`，标题 `每日AI热点新闻（试运营）`
    - 邮件正文为 HTML 内容
    - **如有播客音频**，将音频文件作为邮件附件发送
    - ⛔ **邮件格式要求**：用 `MIMEMultipart('alternative')`，纯文本作为 plain part + HTML 作为 html part。**绝对禁止把 HTML 文件作为附件发送**，HTML 必须是邮件正文（2026-04-21 事故：发成了附件导致收件人看到的是纯文本"请查看附件"）。不要用 `MIMEMultipart('mixed')` 除非有播客音频附件
    - 如有播客附件，则用 `MIMEMultipart('mixed')`，内部先放 `MIMEMultipart('alternative')`（text+html），再放音频附件
    - ⛔ **发送规则**：
      - 收件人必须只来自 `references/send-email-config.json` 解析出的 audience
      - `references/recipients.json` 必须是非空 JSON 对象，每个 audience 是非空字符串数组，邮箱格式合法且不得重复
      - 禁止读取、恢复或使用历史全员名单
      - 每封邮件之间间隔 **8-10 秒**
      - 每发 **10 封**后暂停 **30 秒**
      - 如果收到 451/421/550 错误（频率限制），暂停 **60 秒**后重连重试，最多重试 3 次
      - 163 邮箱日发送配额有限，带大附件时更容易触发限流
  - 📱 飞书：**⏸️ 暂停**（access token 过期，待重新配置飞书应用后恢复）
  - 📄 飞书文档备份：**⏸️ 暂停**（同上）
  - 🔼 全员发送前后端上传：
    - 由 workflow 的 `send_files` 控制；定时自动触发时必须视为 true。
    - 手动调试时 `send_files` 只控制是否上传文件，不控制是否发邮件。
    - 配置来源：`references/send-file-config.json`
    - 调用 `scripts/upload_delivery_artifacts.py --date YYYY-MM-DD`。
    - endpoint 优先用 `AI_DAILY_PRE_SEND_API_URL` 临时覆盖，否则读取 `references/send-file-config.json`，禁止在临时脚本中另写地址。
    - 如果同一次运行中 `send_files=true` 且 `send_email=true`，上传失败必须阻断全员发送。
  - 📧 全员邮件发送：
    - 由 workflow 的 `send_email` 控制；定时自动触发时必须视为 true。
    - `send_email` 只控制邮件，不控制后端上传。
  - 📝 发送日志：写入 `references/send-log.md`（日期 + 条数 + 各渠道状态 + 播客合成状态）
  - ⛔ **发送结果以 `scripts/send_all.py` stdout 为准**，成功条件为输出 `成功: N / N` 且进程退出码为 0
- **容错**：某渠道失败记录原因，不阻塞其他渠道

### Step 4.5: HTML 留样
- 将最终 HTML 复制保存到 `samples/YYYY-MM-DD.html`（YYYY-MM-DD 为执行日期）
- 确保 `samples/` 目录存在（`mkdir -p`）
- 文件名示例：`samples/2026-04-03.html`
- 此步骤在分发（Step 4）完成后、收尾（Step 5）前执行

### Step 4.6: 14:30 测试发送质量门禁（给独立 cron 用）
- **⛔ 禁止再使用旧门禁：** `hubtoday_count > 0` / `<p>` 标签数量 > 0
- 当前 HTML 模板允许使用 `table/div/td` 结构，**`<p>` 数量为 0 不代表异常**
- 当前数据源已切换，**聚合源文案和域名都必须为 0 才算通过**（`hubtoday` / `hex2077` / `hextra` / `aibase.com`）
- 推荐门禁规则：
  1. `/tmp/ai-daily-news-html-YYYY-MM-DD.html` 存在且大小 ≥ 15KB
  2. `/tmp/ai-daily-news-podcast-YYYY-MM-DD.mp3` 存在且大小在 1MB–8MB
  3. `samples/YYYY-MM-DD.html` 存在（说明 review 已发）
  4. HTML 中聚合源/禁用域名计数为 0：`hubtoday`、`hex2077`、`hextra`、`aibase.com`、`wappoc_appmsgcaptcha`、`mp.weixin.qq.com/mp/wappoc`
  5. 提取唯一新闻原文链接数 ≥ 8，且不得为站点首页根路径
  6. 正文块统计需兼容 `<div>` / `<p>` / `<td>`，去标签后 ≥80 字的正文块至少 8 个
- **只有以上门禁全部通过，才允许执行仓库内受控发送器；上午使用 `--phase morning`，下午使用 `--phase afternoon`**

### Step 5: 收尾
- 更新 `references/recent-issues-state.md`
- **⛔ 强制留痕日志（每次必须执行，不可跳过）**：将本次执行结果写入 `logs/YYYY-MM-DD.md`，内容包括：
  - 各步骤状态（✅/❌）+ 数据条数 + HTML大小 + 播客时长/大小
  - Review 邮件：audience 名称、收件人列表 + SMTP 实际执行结果
  - 发送结果：`references/recipients.json` 指定 audience 中各收件人的成功或失败状态
  - 故障记录（如有）
  - 日志目录固定为 `logs/`（skill 目录下持久化存储，不用 /tmp）
- 返回执行摘要（条数、各渠道状态、播客时长、异常记录）

---

## 关键文件索引
| 文件 | 用途 |
|------|------|
| `references/fault-prevention.md` | 禁止规则 + 预检 + 自检清单 |
| `references/content-rules.md` | 栏目结构、正文要求、锐评、去重 |
| `references/html-design.md` | HTML 配色、字体、结构规范 |
| `references/smtp-config.md` | SMTP 配置 |
| `references/recipients.json` | 邮件收件人 |
| `references/send-email-config.json` | 邮件 phase、audience、标题后缀和节流配置 |
| `references/send-file-config.json` | 全员发送前后端上传配置 |
| `references/recent-issues-state.md` | 跨天去重状态 |
| `references/rss-radar-sources.md` | RSS 源配置 |
| `templates/v4-2026-03-18.html` | HTML 模板参考 |
| `samples/YYYY-MM-DD.html` | 每日 HTML 留样归档 |

## ⛔ 执行纪律（必须遵守）

**⛔ 禁止使用 `sessions_spawn` 和 `sessions_yield`**。在 cron isolated session 中 yield 后子代理完成的事件无法可靠恢复主 session 执行上下文，导致后续步骤全部跳过（2026-04-21 事故根因）。

所有步骤必须在**同一个 session 内串行执行**，数据采集和播客合成用 `exec` 后台运行 + `process poll` 等待结果，不用子代理。

邮件只能发送一次，必须按以下严格串行顺序执行：

1. **Step 1**: 预检（主 session，exec 逐项检查）
2. **Step 2**: 数据采集 → 用 `exec` 后台跑 python 脚本 → `process poll` 等待完成 → `read` 结果 JSON
3. **Step 3**: 生成 HTML（主 session）
4. **Step 3.5**: 播客合成 → 用 `exec` 后台跑 mosi_dialogue.sh 分段合成 → `process poll` 等待（超时 20 分钟）→ 失败则重试一次 → 再失败放弃播客
5. **Step 4**: 分发（主 session，exec 发 SMTP 邮件）
6. **Step 4.5-5**: HTML 留样 + 收尾

## 时间预算（25 min 内）
预检 1min → web_fetch 2min → URL实检 3min → 生成HTML 3min → 播客脚本 2min → 播客合成 8min → 邮件发送 2min → 收尾 1min ≈ 22min
