
## 2026-06-21 11:30 (cron auto)
- 条数: 13（采集22条，入选13条）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 3.29MB）
- 播客: ✅ 合成成功 7m11s（MOSI TTS 老陈+小满，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: 预检时直接 urllib 访问静态日报页返回 403，改用 web_fetch 复核后继续；自动任务按本次要求仅发送 yangyc13@lenovo.com

## 2026-06-02 11:30 (cron auto)
- 条数: 13
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 4.11MB）
- 播客: ✅ 合成成功 8m59s（MOSI TTS 老陈+小满）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: NVIDIA Robotaxi 官方新闻页被 403 拦截，保留官方链接并依据当日汇总页与链接标题撰写；仅按自动任务要求发送给 yangyc13@lenovo.com

## 2026-05-07 11:30 (cron auto)
- 条数: 14
- 邮件: ✅ yangyc13@lenovo.com + penglei4@lenovo.com（含播客附件 1.9MB）
- 播客: ✅ 合成成功 4m09s（MOSI TTS 老陈+小满）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: HubToday 主站已迁移至 hex2077.dev，SPA 无法直接抓取，改用 AIbase 新闻源

## 2026-04-28 17:16 (cron auto)
- 条数: 14
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 11.7MB）
- 播客: ✅ 合成成功 12m10s（MOSI TTS 老陈+小满）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停

## 2026-04-23 13:14 (强制重跑)
- 条数: 21
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 5.81MB）
- 播客: ✅ 合成成功 6m20s（SiliconFlow MOSS-TTSD-v0.5 voice preset: benjamin + anna）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: references 方式报 500，改用 voice preset；ChatGPT 表格插件 URL 跳过

## 2026-04-23 11:30 (首次自动)
- 条数: 13（10条通过验证）
- 邮件: ✅ yangyc13@lenovo.com
- 播客: ⏭️ 跳过（参考音频未部署）
- 飞书: ❌ access token 过期
- 飞书文档: ❌ 同上

---

## 2026-04-21 12:40:28

### 发送概况
- 总新闻数：15
- 邮件发送：SUCCESS
- 飞书消息：FAILED
- 文档备份：FAILED
- 播客合成：FAILED

### 详细状态
- 邮件收件人：yangyc13@lenovo.com
- 飞书群ID：oc_d965563ed9278d20b223dc61aa49162f
- HTML文件：True
- 飞书文件：True

---
## 2026-04-21 12:39:57

### 发送概况
- 总新闻数：15
- 邮件发送：FAILED
- 飞书消息：FAILED
- 文档备份：FAILED
- 播客合成：FAILED

### 详细状态
- 邮件收件人：yangyc13@lenovo.com
- 飞书群ID：oc_d965563ed9278d20b223dc61aa49162f
- HTML文件：True
- 飞书文件：True

---
## 2026-04-07
- 条数: 14
- 邮件: 成功 (11/11收件人全部发送成功)
  - yangyc13@lenovo.com ✅
  - zhanghq24@lenovo.com ✅
  - renjc5@lenovo.com ✅
  - hujun10@lenovo.com ✅
  - penglei4@lenovo.com ✅
  - xiongjb2@lenovo.com ✅
  - zhengqh2@lenovo.com ✅
  - zhury2@lenovo.com ✅
  - gaoxi1@lenovo.com ✅
  - lixl72@lenovo.com ✅
  - heyj17@lenovo.com ✅
- 飞书: 失败 (Bot无权限发送给石头 ou_0ef450a9114d1fe28e69679c82ca1170，错误: "Bot has NO availability to this user")
- 飞书文档: 成功 (doc_id: CQQ3dmS8doxBT8xEhVMcIch7n3c, URL: https://www.feishu.cn/wiki/L1jBw4IOqiA4rUkmx04cea0SnEf)
- 异常记录:
  - 飞书消息发送失败：Bot 对目标用户不可见，需在飞书开放平台将应用可见范围设置为全公司或添加该用户
  - feishu_doc 工具返回 403，改用 lark-cli 以 user 身份创建文档成功

## 2026-04-09
- **条数**: 9条（目标12-15，因HubToday页面不可用改用web_search采集，不足未补位）
- **飞书消息**: ❌ 发送失败（400错误，target ou_0ef450a9114d1fe28e69679c82ca1170 不可达）
- **邮件**: ⏭ 跳过（SMTP配置未读取）
- **飞书文档备份**: ⏭ 跳过
- **播客合成**: ⏭ 跳过
- **HTML留样**: ✅ samples/2026-04-09.html
- **状态更新**: ✅ references/recent-issues-state.md
- **异常记录**:
  - HubToday页面 `https://ai.hubtoday.app/2026-04/2026-04-09` 返回404，改用web_search+web_crawl采集
  - 子代理A数据采集结果未能回传，改为手动执行
  - 飞书消息发送两次均返回400，疑似target ID权限问题

## 2026-04-09
- 条数：14
- 邮件：✅ 成功（SMTP 163.com，11位收件人，HTML正文+wav附件）
- 飞书：✅ 成功（P2P聊天 oc_d965563ed9278d20b223dc61aa49162f，分4条发送文本+1条文件链接）
- 飞书文档：✅ 成功（docx/UrC8d2QuuodubSxa7SZcfDpjnLc，父节点 MUQnwmyFni4W1OkNWMxcMlEZn2g）
- 播客：⚠️ 部分成功（文本+链接已发送，语音气泡发送失败，改为文件链接）

### 2026-04-11
- 条数：14
- 邮件：✅ 已发送（yangyc13@lenovo.com，含播客附件4.7MB）
- 飞书群：✅ 已发送（6条消息）
- 文档备份：✅ 已创建（docx/F5sgdbL6XoR3eTxqM6scdAZSnmh，未移入知识库）
- 播客：✅ 5分钟305秒
- HTML留样：✅ samples/2026-04-11.html

## 2026-04-12
- 条数: 11
- 邮件: yangyc13@lenovo.com ✓
- 飞书群: oc_d965563ed9278d20b223dc61aa49162f ✓
- 飞书文档: AI每日热点 2026-04-12 ✓
- 播客: 9m18s ✓
| 2026-04-13 | 12条 | 邮件:成功 | 飞书:成功 | 文档:部分成功(未移入知识库) | 播客:成功(5.9MB) |
| 2026-04-14 | 13条 | 邮件:成功 | 飞书:成功 | 文档:成功 | 播客:成功(10m22s) |

## 2026-04-16
- 条数: 13
- 邮件: 成功 (review模式，仅发送yangyc13@lenovo.com，含播客附件6MB)
- 飞书群: 成功 (oc_d965563ed9278d20b223dc61aa49162f，4条消息)
- 飞书文档: 失败 (403权限不足)
- HTML留样: 成功 (samples/2026-04-16.html)
- 播客: 成功 (SiliconFlow MOSS-TTSD-v0.5，~6.5分钟，6MB)
- 异常: 飞书文档403权限不足，未创建备份

## 2026-04-29
- 日期: 2026-04-29 12:30 (Asia/Shanghai)
- 条数: 14条（1焦点 + 6产品 + 5研究 + 1行业 + 1焦点=14总计）
- 邮件: ✅ 发送至 yangyc13@lenovo.com
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 播客: ✅ 4分51秒，2.3MB，64k MP3，含附件
- 数据淘汰: 1条(qbitai超时) - Cursor删库事故
- 异常: 无
## 2026-05-01
- 条数: 12条（精选自22条验证通过）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 播客: ✅ 时长 5分17秒，2.5MB，64k MP3
- 异常: 无

## 2026-05-01
- 条数: 12条（精选自22条验证通过）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 播客: ✅ 时长5分17秒，2.5MB，64k MP3
- 异常: 无

## 2026-05-02
- 日期: 2026-05-02 11:30 (Asia/Shanghai)
- 新闻条数: 16条
- 邮件: SUCCESS → yangyc13@lenovo.com (review only)
- 飞书消息: 暂停
- 飞书文档: 暂停
- 播客: SUCCESS | 时长: 3分59秒 | 大小: 1.83MB | 64k MP3
- 异常: 无

## 2026-05-03
- 日期: 2026-05-03 11:30 (Asia/Shanghai)
- 新闻条数: 15
- 邮件: ✅ yangyc13@lenovo.com (review only, 含播客附件)
- 飞书消息: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 播客: ✅ 196s (3min16s), 1.5MB, 64k MP3
- 异常: 无

## 2026-05-04
- 日期: 2026-05-04 11:30 (Asia/Shanghai)
- 采集条数: 15条（清除3条微信验证码链接后保留12条）
- 邮件: 成功发送至 yangyc13@lenovo.com（review版）
- 飞书消息: 暂停
- 飞书文档: 暂停
- 播客: 成功合成，时长311秒(5.2分钟)，大小2.4MB，64k码率
- 异常: 3条微信公众号链接重定向至wappoc验证码页面，已按规则淘汰（硅谷CTO/Anthropic年化收入/DeepSeek V4）
## 2026-05-05 | 14条 | 邮件:yangyc13@lenovo.com ✅ | 飞书:暂停 | 播客:3分57秒,1.8MB ✅ | 跳过:1条(OpenAI 403)
2026-05-06 | 15条 | 邮件(yangyc13@lenovo.com)✅ | 播客4分32秒 2.1MB ✅ | 飞书⏸️ | HTML留样✅

## 2026-05-09
- 日期: 2026-05-09 (周六)
- 新闻条数: 11
- 邮件: yangyc13@lenovo.com ✅, penglei4@lenovo.com ✅
- 播客: 4分5秒, 1.9MB, 附件发送 ✅
- 飞书: 暂停
- 飞书文档: 暂停
- HTML: samples/2026-05-09.html

## 2026-05-11
- 日期: 2026-05-11 11:30 (Asia/Shanghai)
- 新闻条数: 12
- 邮件: yangyc13@lenovo.com ✅（含播客附件）
- 播客: 7分12秒, 3.3MB, 64k MP3 ✅
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-11.html
- 异常: SMTP 预检命令返回码异常但握手成功；按实际连通性继续执行



## 2026-05-12
- 日期: 2026-05-12 11:30 (Asia/Shanghai)
- 新闻条数: 13
- 邮件: yangyc13@lenovo.com ✅（含播客附件）
- 播客: 6分08秒, 2.94MB, 64k MP3 ✅
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-12.html
- 异常: 无

## 2026-05-13
- 日期: 2026-05-13 11:30 (Asia/Shanghai)
- 新闻条数: 12
- 邮件: yangyc13@lenovo.com ✅（含播客附件）
- 播客: 6分01秒, 2.76MB, 64k MP3 ✅
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-13.html
- 异常: 播客首次合成参数错误，重试后成功

## 2026-05-14
- 日期: 2026-05-14 11:30 (Asia/Shanghai)
- 新闻条数: 8
- 邮件: yangyc13@lenovo.com ✅（含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-14.mp3 duration_sec=358 size_bytes=2867949 parts=6
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-14.html

## 2026-05-15
- 日期: 2026-05-15 11:30 (Asia/Shanghai)
- 新闻条数: 14
- 邮件: yangyc13@lenovo.com ✅（含播客附件）
- 播客: 7分58秒, 3.83MB, 64k MP3 ✅
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-15.html
- 异常: 播客首次合成参数写成 --input，按脚本帮助修正为 --text 后重试成功


## 2026-05-16
- 日期: 2026-05-16 11:30 (Asia/Shanghai)
- 新闻条数: 10
- 邮件: yangyc13@lenovo.com ✅（含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-16.mp3 duration_sec=395 size_bytes=3163629 parts=3
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-16.html
- 异常: hex2077 当日页 404；browser tool 不可用；改用 qbitai/36kr 批量抓取并校验

## 2026-05-20
- 日期: 2026-05-20 15:34 (Asia/Shanghai)
- 新闻条数: 12
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-20.mp3 duration_sec=475 size_bytes=3804141 parts=6
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-20.html
- 异常: SMTP 预检脚本首次误读退出码，但握手成功后已继续；OpenAI 内容溯源页与 BIP 论文链接未通过批量验证，按规则淘汰


## 2026-05-21
- 日期: 2026-05-21 21:28 (Asia/Shanghai)
- 新闻条数: 13
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令单人补发，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-21.mp3 duration_sec=338 size_bytes=2705901 parts=6
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-21.html
- 异常: 11:30 被旧 SMTP 预检误杀；21:28 手动重跑并补发成功；预检已改为 smtp_probe.py + 握手内容判定 + 587 STARTTLS 兜底

## 2026-05-22
- 日期: 2026-05-22 11:30 (Asia/Shanghai)
- 新闻条数: 15
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-22.mp3 duration_sec=672.1 size_bytes=5377389 bitrate=64k
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-22.html
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；已继续执行并使用 HubToday→hex2077 当天静态页 + 单脚本批量校验完成采集

## 2026-05-23
- 日期: 2026-05-23 11:30 (Asia/Shanghai)
- 新闻条数: 12
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-23.mp3 duration_sec=492.8 size_bytes=3942381 parts=4
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-23.html
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；已继续执行并使用 hex2077 当天静态页 + 单脚本批量校验完成采集

## 2026-05-24
- 日期: 2026-05-24 11:30 (Asia/Shanghai)
- 新闻条数: 12（14条验证通过后，去除2条近三日重复选题）
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-24.mp3 duration_sec=457.3 size_bytes=3658989 parts=4
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-24.html
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；采集首轮因标题重合度规则偏严淘汰5条，二轮按真实页面标题修正后恢复到14条有效候选

## 2026-05-25
- 日期: 2026-05-25 11:30 (Asia/Shanghai)
- 新闻条数: 12（15条验证通过后，去除2条近三日重复选题与1条低优先级开源项目）
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-25.mp3 duration_sec=506.1 size_bytes=4048749 bitrate=64k parts=4
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-25.html
- 异常: qbitai 首页 web_fetch 403；2条微信公众号原文跳转到 wappoc 验证页已淘汰；AGENTS.md 指向的 web-tools-guide 缺失，已沿用 hex2077 静态页 + 单脚本批量校验继续执行

## 2026-05-26
- 日期: 2026-05-26 11:30 (Asia/Shanghai)
- 新闻条数: 13
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-26.mp3 duration_sec=499.4 size_bytes=3995565 bitrate=64k parts=5
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-26.html
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；qbitai 首页 web_fetch 403，已改用 hex2077 当日静态页 + 单脚本批量校验继续执行

## 2026-05-27
- 日期: 2026-05-27 11:30 (Asia/Shanghai)
- 新闻条数: 12
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-27.mp3 duration_sec=432.3 size_bytes=3458541 bitrate=64k parts=4
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-27.html
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；qbitai 首页 web_fetch 403，已改用 hex2077 当日静态页 + 单脚本批量校验继续执行

## 2026-05-28
- 日期: 2026-05-28 11:30 (Asia/Shanghai)
- 新闻条数: 13
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-28.mp3 duration_sec=554.7 size_bytes=4437741 bitrate=64k parts=6
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-28.html
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；按现行可用链路使用 hex2077 当日静态页（HubToday 归档页）+ 单脚本批量校验继续执行；x.ai 页面 web_fetch 403，但未影响原文链接保留与播客/邮件发送
## 2026-05-29
- 条数：13
- 邮件：SUCCESS（yangyc13@lenovo.com，含 MP3 附件）
- 飞书消息：SKIPPED（已暂停）
- 飞书文档：SKIPPED（已暂停）
- 播客：SUCCESS（SUCCESS; mp3=/tmp/ai-daily-news-podcast-2026-05-29.mp3; wav=/tmp/ai-daily-news-podcast-2026-05-29.wav; duration_sec=505.7; size_bytes=4046061; parts=5）

## 2026-05-30
- 日期: 2026-05-30 11:30 (Asia/Shanghai)
- 新闻条数: 15
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-30.mp3 duration_sec=479.6 size_bytes=3836781 parts=4
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-30.html
- 异常: qbitai 首页 web_fetch 403、36kr AI 页正文不可读；按现行链路使用 hex2077 2026-05-30 静态页 + 单脚本批量校验完成采集，微信验证码 URL 过滤后无命中

## 2026-05-31
- 日期: 2026-05-31 11:30 (Asia/Shanghai)
- 新闻条数: 13
- 邮件: yangyc13@lenovo.com ✅（按本次 cron 指令仅发单人，含播客附件）
- 播客: SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-05-31.mp3 duration_sec=483.648000 size_bytes=3869421 bitrate=64k parts=6
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-05-31.html
- 异常: hex2077 当日静态页 404；已按规则记录并改用 qbitai 最新页 + AITNT 当日页批量校验继续执行


## 2026-06-01
- 条数：14
- 邮件：✅ review 已发送（yangyc13@lenovo.com）
- 飞书消息：⏸️ 已暂停
- 飞书文档：⏸️ 已暂停
- 播客：✅ 446.1s / 3568749 bytes
- 异常：france24 403 1条淘汰；ScienceDaily 首页链接 1 条淘汰

## 2026-06-03
- 条数：14
- 邮件（review）：✅ 已发送至 yangyc13@lenovo.com
- 邮件（全员）：⏸️ 未触发
- 飞书消息：⏸️ 已暂停
- 飞书文档备份：⏸️ 已暂停
- 播客：✅ 461.3s / 3690861 bytes / 4 段

- 2026-06-04 | 条数: 13 | 邮件: ✅ review 发至 yangyc13@lenovo.com | 播客: ✅ | 飞书消息: ⏸️ | 飞书文档: ⏸️

## 2026-06-05 11:30 (cron auto)
- 条数: 12（29条候选中14条通过批量实检，精选12条发送）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 4.01MB）
- 播客: ✅ 合成成功 8m46s（MOSI TTS 老陈+小满，5段，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；按当前可用链路继续执行，使用 hex2077 当日静态页（HubToday 归档页）+ 单脚本批量校验完成采集；按本次 cron 指令仅发送 yangyc13@lenovo.com

## 2026-06-06 11:30 (cron auto)
- 条数: 12（hex2077 归档页采集，批量校验后精选 12 条）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 3.15MB）
- 播客: ✅ 合成成功 6m33.7s（MOSI TTS 老陈+小满，6段，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；按当前可用链路继续执行，使用 hex2077 当日静态页（HubToday 归档页）+ 单脚本批量校验完成采集；按本次 cron 指令仅发送 yangyc13@lenovo.com；AIbase 链接已剔除未进入最终 HTML


## 2026-06-07 11:30 (cron auto)
- 条数: 12（hex2077 当日静态页采集，23 条候选批量校验后 21 条有效，精选 12 条发送）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 3.45MB）
- 播客: ✅ 合成成功 7.5m（MOSI TTS 老陈+小满，6段，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: 2 条微信公众号原文链接跳转到 wappoc 验证页，已按规则淘汰；AGENTS.md 指向的 web-tools-guide 缺失，已继续按当前可用链路执行；按本次 cron 指令仅发送 yangyc13@lenovo.com

## 2026-06-08 11:30 (cron auto)
- 条数: 14
- 邮件: ✅ yangyc13@lenovo.com（含播客附件）
- 播客: ✅ 合成成功 7.5m（MOSI TTS 老陈+小满，4段，3.43MB，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: 2 条候选被批量实检淘汰（Gemini Live 链接 404；黄仁勋访韩条目标题匹配不足）；按本次 cron 指令仅发送 yangyc13@lenovo.com
## 2026-06-09 11:30 (cron auto)
- 条数: 12（28 条候选批量校验后 14 条有效，精选 12 条发送）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 3.14MB）
- 播客: ✅ 合成成功 6m32.3s（MOSI TTS 老陈+小满，5 段，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；预检阶段直连源页返回 403，已按现行链路改用 web_fetch 成功抓取静态页；按本次 cron 指令仅发送 yangyc13@lenovo.com

## 2026-06-10 11:30 (cron auto)
- 条数: 13（hex2077 静态日报页采集，22 条候选批量校验后 13 条有效并全部入选）
- 邮件: ✅ yangyc13@lenovo.com（按本次 cron 指令仅发单人，含播客附件 3.47MB）
- 播客: ✅ 合成成功 7分14秒（MOSI TTS 老陈+小满，3 段，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-06-10.html
- 异常: 无

## 2026-06-11 11:30 (cron auto)
- 条数: 9（hex2077 静态日报页采集，9 条候选批量校验后 9 条有效并全部入选）
- 邮件: ✅ yangyc13@lenovo.com（按本次 cron 指令仅发单人，含播客附件 4.70MB）
- 播客: ✅ 合成成功 9分47.7秒（MOSI TTS 老陈+小满，4 段，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-06-11.html
- 异常: 无

## 2026-06-12 11:30 (cron auto)
- 条数: 12（hex2077 静态日报页采集，28 条候选批量校验后 25 条有效，精选 12 条发送）
- 邮件: ✅ yangyc13@lenovo.com（按本次 cron 指令仅发单人，含播客附件 3.08MB）
- 播客: ✅ 合成成功 6分24.7秒（MOSI TTS 老陈+小满，5 段，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-06-12.html
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；qbitai 首页 web_fetch 403；采集阶段另有 3 条候选被批量实检淘汰；按本次 cron 指令仅发送 yangyc13@lenovo.com

## 2026-06-13 11:30 (cron auto)
- 条数: 12（hex2077 静态日报页采集，24 条候选批量校验后 23 条有效，精选 12 条发送）
- 邮件: ✅ yangyc13@lenovo.com（按本次 cron 指令仅发单人，含播客附件）
- 播客: ✅ SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-06-13.mp3 wav=/tmp/ai-daily-news-podcast-2026-06-13.wav duration_sec=628.128000 size_bytes=5025261 bitrate=64k parts=6
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；Reuters 原文页被 JS/反爬拦截，保留 Reuters 原始文章链接并依据汇总页摘要撰写；按本次 cron 指令仅发送 yangyc13@lenovo.com

## 2026-06-14 11:30 (cron auto)
- 条数: 14（26 条候选批量校验后 24 条有效，精选 14 条发送）
- 邮件: ✅ yangyc13@lenovo.com（按本次 cron 指令仅发单人，含播客附件 4.11MB）
- 播客: ✅ 合成成功 8分33.9秒（MOSI TTS 老陈+小满，4 段，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-06-14.html
- 异常: 2 条候选被批量实检淘汰（Google News RSS 落地页正文不足；News Hacker 目标页不可读）；按本次 cron 指令仅发送 yangyc13@lenovo.com

## 2026-06-15 11:30 (cron auto)
- 条数: 13（26 条候选批量校验后 17 条有效，补抓 3 条真实来源后共 20 条有效，精选 13 条发送）
- 邮件: ✅ yangyc13@lenovo.com（按本次 cron 指令仅发单人，含播客附件 3.10MB）
- 播客: ✅ SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-06-15.mp3 wav=/tmp/ai-daily-news-podcast-2026-06-15.wav duration_sec=388.056000 size_bytes=3104685 bitrate=64k parts=4
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- HTML: samples/2026-06-15.html
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；qbitai 首页 web_fetch 403；36kr AI 页可访问但正文抽取失败，仅保留页脚；主源与昨日报高度重合，补抓讯飞 X2-VL、AI 版支付宝、WSJ 校园 deepfake 文章以满足去重要求；按本次 cron 指令仅发送 yangyc13@lenovo.com


## 2026-06-16 11:30 (cron auto)
- 条数: 13
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 3.25MB）
- 播客: ✅ 合成成功 7.1m（MOSI TTS 老陈+小满，64k MP3）
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: AGENTS.md 指向的 web-tools-guide 缺失；按当前可用链路继续执行，仅发送给 yangyc13@lenovo.com


## 2026-06-17 14:xx (manual rerun)
- 条数: 12（31 条候选批量实检后 21 条有效，精选 12 条发送）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 3.42MB）
- 播客: ✅ 合成成功 7分07.7秒（MOSI TTS 老陈+小满，5 段，64k MP3）
- 飞书: ⏸️ 跳过
- 飞书文档: ⏸️ 跳过
- 异常: 11:30 cron run 的 provider/model payload 失败未复现；本次在普通会话内手动重跑完成。


## 2026-06-18 11:30 (cron auto)
- 条数: 13（hex 静态页 404，改用备用真实来源并完成批量校验）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 3.30MB）
- 播客: ✅ SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-06-18.mp3 wav=/tmp/ai-daily-news-podcast-2026-06-18.wav duration_sec=413.016000 size_bytes=3304365 parts=5
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: hex2077 当日静态页 404；按规则改用备用真实来源，未在成稿中保留聚合源名称或链接

## 2026-06-19 11:30 (cron auto)
- 条数: 13（24 条候选批量校验后 15 条有效，精选 13 条发送）
- 邮件: ✅ yangyc13@lenovo.com（含播客附件 3.81MB）
- 播客: ✅ SUCCESS mp3=/tmp/ai-daily-news-podcast-2026-06-19.mp3 wav=/tmp/ai-daily-news-podcast-2026-06-19.wav duration_sec=476.4 size_bytes=3811821 parts=4
- 飞书: ⏸️ 暂停
- 飞书文档: ⏸️ 暂停
- 异常: qbitai 原文页 web_fetch 403，但 requests 批量实检可达；x.ai 原文页 403 未入稿；按本次 cron 指令仅发送 yangyc13@lenovo.com

## 2026-06-20
- 条数：15
- 邮件：✅ review 已发送至 yangyc13@lenovo.com（附播客 MP3）
- 飞书消息：⏸️ 已暂停
- 飞书文档备份：⏸️ 已暂停
- 播客：✅ ai-daily-news-podcast-2026-06-20.mp3
