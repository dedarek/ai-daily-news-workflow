# 故障预防 & 约束规则

## ⛔ 硬性禁止（违反即事故）

| # | 规则 | 对应历史事故 |
|---|------|-------------|
| 1 | 禁止使用 HubToday 来源页面链接（ai.hubtoday.app/...） | 邮件中出现了 hubtoday 链接，Outlook safelinks 包装后更明显 |
| 9 | 禁止使用 AIbase 链接作为原文链接（www.aibase.com/...） | AIbase 是数据采集源，不是原文来源，链接不得出现在邮件正文中。必须从 AIbase 文章中提取原始来源链接（The Verge/TechCrunch/官方博客等），无法获取原始链接则淘汰该条 |
| 10 | 同一事件禁止重复收录 | AIbase 会对同一事件发多篇报道，必须去重：相同事件只保留信息量最大的一条，其余淘汰 |
| 2 | 禁止出现聚合源名称或来源标签（`HubToday`、`hex2077`、`Hextra`、`AIbase` 等） | 2026-06-08 邮件正文多次提到 HubToday，读感像在转述聚合页而不是原文 |
| 3 | Hextra 源已移除，不要尝试获取 | 尝试访问已下线服务导致浪费时间 |
| 4 | 禁止链接指向网站首页（必须指向具体文章子路径） | 链接张冠李戴，正文内容与链接不匹配 |
| 5 | 禁止将多条新闻压缩为单行摘要 | 飞书消息可读性极差 |
| 6 | 每条新闻正文不少于 4 句话 | 某些条目只有1-2句话，信息量不足 |
| 7 | 正文描述必须来自链接指向的原文 | 内容与链接不匹配，读者点击后发现文不对题 |
| 8 | 所有链接必须在采集阶段通过实检验证（见链接实检规则） | 链接 404 或页面内容与新闻不匹配 |

## 链接实检规则（2026-04-02 新增）

**所有链接必须在采集阶段通过验证，未验证的链接不得进入最终内容。**

### 子代理采集时的验证步骤
对每个候选 URL，按顺序执行：

1. **HTTP HEAD 检查** — `curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 URL`
   - 返回 200/301/302 → 继续
   - 返回 404/403/503/timeout → **直接淘汰，不补位**

2. **跟随重定向** — 对 301/302 响应，`curl -sSL -o /dev/null -w "%{url_effective}" URL` 拿到最终 URL
   - 如果最终 URL 仍是 hubtoday.app 中间页 → 淘汰
   - 如果最终 URL 和原始 URL 不同，使用最终 URL

3. **页面标题匹配** — 抓取页面 `<title>` 标签内容，与新闻标题做关键词重合度检查
   - 重合度 < 30% → **淘汰**（内容明显不匹配）
   - 30%-50% → 标记为「低置信度」，正文撰写时需谨慎，只用原文确认的内容
   - > 50% → 通过

4. **正文有效性检查** — 提取页面正文前 500 字，检查是否包含以下无效标记：
   - 「页面不存在」「404 Not Found」「正在维护」「验证码」「登录后查看」「付费墙」
   - 页面纯空白或正文 < 100 字 → **淘汰**

### HubToday 链接特别处理
- HubToday 的 URL 经常是中间页（带重定向），**禁止直接使用 hubtoday.app 链接**
- 必须跟随重定向拿到真实原文 URL，再对真实 URL 做上述验证
- 重定向失败或目标 404 → 淘汰该条新闻

### 补充搜索时的链接偏好
- 优先选一手源：官方博客、GitHub、ArXiv、主流科技媒体（The Verge / TechCrunch / Ars Technica 等）
- 避免转载站、聚合站、SEO 农场

### 最终生成前复查
- 在 Step 3 生成内容之前，对 JSON 里所有 URL 做一次快速 HEAD 检查（并发执行）
- 任何 URL 此时返回 404/超时 → 从列表中移除，不补位
- 验证结果写入采集日志

## 预检（执行前必做）

在开始任何内容获取之前，必须依次完成：

1. **网络连通性测试**：优先验证当前主数据源可访问。
   - 首选：`hex2077.dev` 日报归档页 `/docs/YYYY-MM/YYYY-MM-DD/`（静态，web_fetch 可抓，自带原文链接）
   - AIbase 已废弃，不再作为必须连通的数据源前置条件
2. **SMTP 连通性测试**：
   - **不要再只看 `openssl s_client` 退出码。** 163 SMTP 可能出现“握手实际成功，但退出码不稳定”的情况。
   - 在 Skill 根目录统一使用脚本：`python3 scripts/smtp_probe.py --json-out /tmp/ai-daily-news-precheck-YYYY-MM-DD.json`
   - 判定规则：只要输出中出现 `CONNECTION ESTABLISHED` / `Protocol version:` / `Verification: OK` / `220` / `221` 任一成功标记，即视为 SMTP 可用
   - **若 465 首次失败，必须重试一次；若仍失败，再自动尝试 587 STARTTLS**；仅在这些探测都失败时才终止
   - ⚠️ 瞬时超时不等于 SMTP 不可用，禁止单次 `timeout 5` 直接判死
3. **工具可用性测试**：
   - **删除 `miaoda-studio-cli` 强制检查**（已不在当前链路中使用）
   - 当前播客链路实际依赖：`bash`、`ffmpeg`、外部 Video API；生成脚本通过 `AI_DAILY_VIDEO_API_TOKEN` 鉴权
4. **磁盘空间检查**：`df -h /tmp | tail -1` 确认有足够空间（>100MB 可用）
5. **日期确认**：输出 `今天是 YYYY-MM-DD`，后续所有 URL 使用该日期

如果以上关键步骤（主数据源 / SMTP 双次失败 / 磁盘空间）失败，**立即终止任务并报告失败原因**，不要继续执行。

## 历史故障 & 预防

### 1. 网络超时处理
- **问题**：HubToday SSL 连接间歇性超时（curl exit code 28/35）
- **预防**：预检失败立即终止，不要继续执行白耗时间
- **重试**：如果 web-crawl 失败，换用 `curl -sL --max-time 20` 直接抓取页面再提取内容

### 2. 禁止出现聚合源链接或聚合源文案
- **问题**：邮件中出现了 ai.hubtoday.app 链接；后续又出现正文多次提到 `HubToday` 的情况，读起来像在复述聚合页
- **预防**：生成 HTML 后，全文大小写不敏感搜索 `hubtoday|hex2077|hextra|aibase`，确保 0 匹配才发送
- **额外要求**：删除所有“HubToday 归档称 / 当日页提到 / 援引聚合页”式句子，只保留能在原文链接中验证的事实

### 3. 执行超时
- **问题**：逐条串行抓取原文导致 20 分钟超时
- **预防**：必须批量并行（同时启动多个 exec），最多抓 10 条原文，其余用摘要
- **时间分配**：预检 1min + HubToday 抓取 2min + 并行原文 5min + 搜索 3min + 生成 5min + 发送 2min = 约 18min

### 4. HTML 生成后自检
- **问题**：链接张冠李戴、内容与链接不匹配
- **预防**：生成 HTML 后，逐条检查：正文中描述的事件能否在对应链接中找到依据
- **额外检查**：`python3 - <<'PY'\nfrom pathlib import Path\nimport re\ntext = Path('output.html').read_text(encoding='utf-8').lower()\nassert not re.search(r'hubtoday|hex2077|hextra|aibase', text), 'aggregator wording leaked into HTML'\nPY` 必须通过

### 5. SMTP 发送失败
- **问题**：SMTP 连接偶尔不稳定，且 `openssl s_client` 在 163 上可能出现“握手成功但退出码异常”，导致预检误杀
- **预防**：预检中测试 SMTP 连通性时必须允许一次重试，并以握手内容判定成功；发送失败时重试一次（间隔 10 秒）
- **禁忌**：禁止用单次 `timeout 5` 的 openssl 探测结果直接终止整条日报流水线；禁止只看 return code 不看 `220/221` / `CONNECTION ESTABLISHED` / `Protocol version`

## 生成后自检清单
- [ ] `python3 - <<'PY'\nfrom pathlib import Path\nimport re\ntext = Path('output.html').read_text(encoding='utf-8').lower()\nassert not re.search(r'hubtoday|hex2077|hextra|aibase', text)\nPY` 通过（聚合源名称/文案为 0）
- [ ] 每条链接不是首页（无 domain.com/ 形式）
- [ ] 每条链接通过 HEAD 检查（非 404/403/503）
- [ ] 每条链接页面标题与新闻标题关键词重合度 ≥ 30%
- [ ] 每条链接页面正文 ≥ 100 字且无无效标记
- [ ] 每条新闻正文 ≥ 4 句话
- [ ] 无来源标签、无元注释
- [ ] 无深色背景 #0F172A
- [ ] 每条新闻都有底部原文链接

### 6. HTML 实体编码乱码（2026-05-06 新增）
- **问题**：HTML 写文件时中文字符被编码成 `&#xXXXX;` 实体，邮件客户端显示乱码
- **根因**：Python 写文件未指定 encoding='utf-8'，或使用了 ascii 模式
- **预防**：写 HTML 文件必须用 `open(path, 'w', encoding='utf-8')`，写完后立即执行验证：
  ```bash
  python3 -c "assert b'&#x' not in open('/tmp/ai-daily-news-html-YYYY-MM-DD.html','rb').read(), 'HTML entity encoding bug!'"
  ```
  验证失败必须重写，绝对不发送含实体编码的 HTML

### 7. 重复发送邮件（2026-05-03 / 2026-05-06 重复出现）
- **问题**：14:30 检查 job 的模型在 SMTP 断连时误判"发送失败"，自己生成了 send-remaining 脚本补发，导致断连前已成功发送的收件人收到两封
- **根因**：send-all 脚本自带断连重连逻辑，已能自动续发；但模型不知道这一点，额外生成补发脚本
- **预防（铁律）**：
  - 每个发送阶段**只允许调用仓库内 `scripts/send_all.py` 一次**
  - 上午发送必须使用 `--phase morning`，下午发送必须使用 `--phase afternoon`
  - phase 到 audience 的映射必须严格来自 `skill/references/send-email-config.json`
  - 收件人必须严格来自 `skill/references/recipients.json` 中对应 audience
  - 禁止调用 `/tmp/send-all-*.py` 或任何历史发送脚本
  - **严禁生成任何 send-remaining / send-partial / retry 等补发脚本**
  - 如果发送脚本退出码非 0，只能报告失败，不能自行补发
- [ ] `python3 -c "assert b'&#x' not in open('output.html','rb').read()"` 通过（无 HTML 实体编码）
- [ ] 当前发送阶段只调用受限发送器一次，收件人仅限对应 audience

### 8. 脚本写完未执行导致邮件未发送（2026-05-07 新增）
- **问题**：cron 生成了 send-email 脚本但没有用 exec 执行，result 文件未写入，review 邮件实际未发出
- **根因**：模型认为"写完脚本"等于"完成发送"，缺少执行+验证闭环
- **预防（铁律）**：
  - 写完发送脚本后必须立即 `exec python3 /tmp/send-email-YYYY-MM-DD.py`
  - 执行后检查 `/tmp/ai-daily-news-result-YYYY-MM-DD.txt` 存在且含 `SUCCESS`
  - 不含 SUCCESS = 发送失败，必须重试一次
  - 禁止只写脚本文件而不执行就结束任务
- [ ] `grep -c "aibase.com" output.html` == 0（禁止 AIbase 链接出现在邮件正文）
- [ ] 无同一事件重复收录（相同核心事件只保留一条）

### 9. 预检规则误杀（2026-05-10 新增，2026-05-21 再修正）
- **问题**：日报 cron 在 Step 1 被过时预检或错误判定拦截，整条流水线未启动
- **根因**：
  1. 仍把 `AIbase` 作为必须连通的数据源前置条件
  2. SMTP 只做一次 `timeout 5` 探测，瞬时抖动即误判失败
  3. 仍检查 `miaoda-studio-cli`，但当前播客链路根本不用它
  4. 仅看 `openssl s_client` return code，不看 163 返回的真实握手内容，导致“实际连通”也被判死
- **预防**：
  - 主数据源改为 `hex2077.dev/docs/...`
  - SMTP 统一改用 `scripts/smtp_probe.py`：465 重试一次，失败再探测 587 STARTTLS，并按握手内容判定成功
  - 删除 `miaoda-studio-cli` 强制预检
  - 仅对当前实际链路依赖做检查（ffmpeg + mosi_dialogue.sh）
  - 预检结果必须落盘为 JSON，便于复盘而不是只留一句 fail/success

---
## 数据源修正记录（2026-05-07）

**错误认知**：hex2077.dev（原 HubToday）已迁移，SPA 渲染，web_fetch 无法抓取 → 改用 AIbase
**实际情况**：
- hex2077.dev **首页** 是 SPA，无法抓取 ✗
- hex2077.dev **`/docs/YYYY-MM/YYYY-MM-DD/` 路径** 是静态文档页，web_fetch 完全可抓 ✓
- 每条新闻自带原文外链（x.com、anthropic.com、arxiv.org、github.com 等）

**正确采集方式**：
```python
URL = f"https://hex2077.dev/docs/{YYYY_MM}/{YYYY_MM_DD}/"
# 解析 <ol> 里的 <li>，提取 <strong> 标题 + 第一个有效外部链接
```

**AIbase 废弃原因**：内容再创作平台，不提供原文跳转链接，违反"原文链接必须指向真实来源"约束。
