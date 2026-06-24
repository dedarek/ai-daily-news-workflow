# Debug Report — AI Daily News 2026-04-03

**排查时间**: 2026-04-03 13:17 CST  
**Session ID**: 29cf2d34-91a8-4004-ae5c-2f54f363b403

---

## 问题 1: 链接是推测构造的，不是真实文章链接

### 原因分析

**HubToday 页面抓取不完整**。web_crawl 抓取 `https://ai.hubtoday.app/2026-04/2026-04-03` 返回的内容中，大量新闻条目的链接位置为空（`- \n\n    - `），说明：

1. HubToday 页面大量内容通过 JavaScript 动态渲染，web_crawl 只能拿到静态 HTML 骨架
2. 新闻条目虽然有标题和摘要，但 `<a href>` 链接为空或被 JS 延迟注入
3. 子代理（数据采集）拿到不完整数据后，**自行推测构造了看似合理的 URL**，而非执行链接实检流程

**关键证据**（对比最近预览文件 `/tmp/ai-daily-news-preview.html`）：
- `https://qwen.aliyun.com/blog/qwen3.6-plus-release` — 路径结构合理但很可能不存在
- `https://azure.microsoft.com/blog/new-ai-models-2026` — 典型推测 URL
- `https://schmidhuber-jepa-controversy.com` — 完全虚构域名
- `https://openrouter.ai/stats/china-growth` — 推测路径

### 根因
子代理在 Step 2（数据采集）中**跳过了链接实检流程**。SKILL.md 明确要求：
1. HTTP HEAD 检查 → 2. 跟随重定向 → 3. 标题匹配 ≥ 30% → 4. 正文 ≥ 100 字

但实际执行中，子代理可能因为：
- HubToday 链接为空，无法跟随重定向，导致后续验证全部跳过
- 时间压力下选择"编造"合理 URL 而非执行补充搜索
- 未将"所有 URL 必须验证"的约束真正落地

### 修复建议
1. **在 Step 2 的子代理 prompt 中增加硬性约束**：如果 HubToday 无有效链接，**必须通过补充搜索（web search）获取真实文章 URL**，禁止自行构造
2. **增加 URL 验证日志**：要求子代理输出每条 URL 的 HEAD 检查结果
3. **在 Step 3 自检中增加 URL 存在性抽检**：随机抽 3 条 URL 做 curl HEAD 验证
4. **考虑用 curl 直接抓 HubToday**（`curl -sL --max-time 20`）作为 web_crawl 的 fallback，因为 curl 可能能拿到更多渲染后的内容

---

## 问题 2: 邮件模板格式偏差

### 排查结果

**对比标准模板 `templates/v4-2026-03-18.html` 和最近预览 `/tmp/ai-daily-news-preview.html`**：

| 项目 | 标准模板 | 04-03 预览 | 状态 |
|------|----------|------------|------|
| 标题栏背景色 | `#3b82f6` | `#3b82f6` | ✅ 一致 |
| 标题栏下边框 | `4px solid #1d4ed8` | `4px solid #1d4ed8` | ✅ 一致 |
| 标题文字颜色 | `#ffffff` | `#ffffff` | ✅ 一致 |
| 卡片背景 | `#ffffff` / `#f8fafc` | `#ffffff` / `#f8fafc` | ✅ 一致 |
| 锐评背景 | `#fffbeb` + `#f59e0b` 左边框 | `#fffbeb` + `#f59e0b` 左边框 | ✅ 一致 |
| 焦点卡片红色边框 | `#fca5a5` + `#ef4444` 左边框 | `#fca5a5` + `#ef4444` 左边框 | ✅ 一致 |
| 栏目标题 | `border-bottom: 2px solid #dbeafe` | `border-bottom: 2px solid #dbeafe` | ✅ 一致 |
| 外层背景 | `#eef1f5` | `#eef1f5` | ✅ 一致 |
| Footer | `#edf0f4` 背景 | `#edf0f4` 背景 | ✅ 一致 |

**结论：HTML 模板结构与配色完全一致**。如果用户反馈"标题栏颜色不对"，可能的原因：
1. **邮件客户端渲染差异**：Outlook 对内联样式的处理与浏览器不同，尤其 `border-radius`、`background-color` 在部分 Outlook 版本中可能被忽略
2. **Outlook Safelinks 改变了链接颜色**：Outlook 会将邮件中的链接替换为 safelinks.protection.outlook.com 包装 URL，可能影响链接文字颜色显示
3. **暗色模式影响**：用户可能在 Outlook 暗色模式下查看，导致蓝色标题栏与深色背景融合

### 修复建议
1. 在 `references/html-design.md` 中增加 **Outlook 兼容性说明**
2. 考虑使用更保守的配色方案，确保在暗色模式下也清晰可辨
3. 增加邮件客户端兼容性测试步骤（发送测试邮件到自己邮箱验证）

---

## 问题 3: 缺少 HTML 留样机制

### 状态
✅ **已修复**。已在 SKILL.md 中新增 Step 4.5（HTML 留样），要求每天将最终 HTML 保存到 `samples/YYYY-MM-DD.html`。

---

## 附加发现

### HubToday 数据质量下降
HubToday 页面的链接数据大量为空（JS 渲染问题），这意味着该数据源的信息提取效率正在下降。建议：
- 评估是否需要添加备用数据源（如 RSS feed、其他 AI 新闻聚合站）
- 或改用 `curl` + HTML 解析替代 web_crawl

### 标准模板本身也有问题
`templates/v4-2026-03-18.html` 中的链接也有不少是首页链接（如 `https://openai.com`、`https://github.com/openclaw`、`https://www.reuters.com`），违反了 fault-prevention.md 的规则 4（禁止链接指向网站首页）。说明模板参考本身就不完美，后续应考虑清理。

---

## 总结

| 问题 | 严重度 | 根因 | 修复状态 |
|------|--------|------|----------|
| 链接虚构 | 🔴 高 | 子代理跳过实检 + HubToday 数据不完整 | ⚠️ 待修复（需加强约束） |
| 模板格式偏差 | 🟡 中 | 可能是邮件客户端渲染差异 | ✅ 模板本身一致 |
| HTML 留样缺失 | 🟢 低 | 流程遗漏 | ✅ 已修复 |
| 标准模板含首页链接 | 🟡 中 | 历史遗留 | ⚠️ 建议清理 |
