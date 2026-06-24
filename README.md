# AI 每日热点新闻 — 完整复现手册

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
- 可选真实发送，唯一收件人为 `yyc54321@126.com`
- 上传 14 天可下载的运行产物

工作流会优先采集当天日报；如果当天页面尚未发布，则最多向前回退 3 天，并在
JSON 运行报告及邮件页脚记录实际内容日期。

## 一、系统概览

每天自动采集 AI 行业新闻，生成 HTML 邮件 + 双人对话播客，分发给团队。

```
11:30  生成 + review 发 yyc54321@126.com
14:30  质量复检 → 仍仅发送测试邮箱
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
| Model | `FunAudioLLM/CosyVoice2-0.5B` |
| 老陈(S1) voice | `FunAudioLLM/CosyVoice2-0.5B:alex` |
| 小满(S2) voice | `FunAudioLLM/CosyVoice2-0.5B:anna` |
| 响应格式 | `response_format: "mp3"` |

⚠️ 这不是 MOSI 官方 API（studio.mosi.cn 的 key 已失效），是硅基流动的 CosyVoice。

### 邮件收件人

**Review 收件人（11:30）**：
- `yyc54321@126.com`

**当前测试收件人（所有流程）**：
- `yyc54321@126.com`
- 发送器带硬限制，任何其他地址都会导致任务终止

---

## 三、每日时间线

```
11:30 CST  ai-daily-news cron 触发
           ├─ Step 1: 预检（~1 min）
           ├─ Step 2: 数据采集 + 链接验证（~5 min）
           ├─ Step 3: HTML 生成 + 质量门禁（~5 min）
           ├─ Step 3.5: 播客合成（~5-8 min）
           ├─ Step 4: 发 review 邮件给 yyc54321@126.com
           └─ Step 5: 留样 + 日志
           
11:30-14:30  管理员（BIL）可审核 review 邮件，有问题可取消

14:30 CST  check-and-distribute cron 触发
           └─ 质量检查通过 → 仅发送 yyc54321@126.com
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
- 逐句调用 SiliconFlow CosyVoice TTS
- ffmpeg concat 拼接所有 MP3 段
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
│   ├── recipients.md           # 唯一测试收件人
│   ├── recent-issues-state.md  # 跨天去重状态
│   └── send-log.md             # 发送日志
├── scripts/
│   ├── check_and_distribute.py # 14:30 质量检查 + send-all
│   ├── validate_html_quality.py # HTML 质量校验
│   ├── smtp_probe.py           # SMTP 预检
│   └── send_all.py             # 测试模式单收件人发送器
├── samples/                    # HTML 留样归档
├── logs/                       # 每日执行日志
└── moss-ttsd/                  # 旧版 TTS 脚本（参考用）
    └── scripts/mosi_dialogue.sh
```

---

## 十、Cron 任务配置

### 任务 1: ai-daily-news
- **时间**：每天 11:30 CST
- **Session**：isolated
- **模型**：无覆盖（使用默认）
- **操作**：读取 SKILL.md 执行完整流程
- **分发**：仅 review 邮件 → yyc54321@126.com

### 任务 2: check-and-distribute
- **时间**：每天 14:30 CST
- **Session**：isolated
- **操作**：运行 `check_and_distribute.py`，通过后仍只发送测试邮箱
- **Auto-send**：无人取消则自动执行

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
- "手动运行，只发 yyc54321@126.com"
- "手动运行，不要转发"
- "手动运行，全程（含播客）"
