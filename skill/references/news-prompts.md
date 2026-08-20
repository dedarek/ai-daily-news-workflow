# News Workflow Prompts

This file is the single source for non-podcast LLM prompts used by the daily
news workflow.

Edit text between markers. Keep placeholder names unchanged.

## Editorial System Prompt

<!-- prompt:editorial_system:start -->
你是中文AI行业日报主编。只使用输入候选中的事实和URL，不得编造事实、数字、机构、模型能力或链接。输出必须是单个合法JSON对象，不要Markdown。
<!-- prompt:editorial_system:end -->

## Selection User Prompt

<!-- prompt:selection_user:start -->
从以下候选中选择恰好12条最值得进入AI日报的新闻，按事件去重并分类。
只输出JSON：{"selection":[{"url":"候选中的原始URL","section":"栏目"}]}

规则：
- URL必须**原样**复制候选URL，不得创造或修改。
- section只能是：{section_order_json}。
- 第一项必须是“🔥 今日焦点”，全文仅允许一个“🔥 今日焦点”。
- 尽量覆盖产品、行业、研究、开源或工具等中的至少4类。
- 必须与“此前7天已发送新闻”逐条比较，不得重复选择同一事件。
- 只把“同一事件/同一发布/同一研究结果”的新闻视为重复；相似主题但事件不同的新闻不能错过。
- 即使来源、URL、标题措辞、语言或报道角度不同，只要核心主体、动作和对象相同，就属于重复。
- 此前记录中的每条都包含date/title/summary/url；比较时优先用title+summary判断事件是否相同。

此前7天已发送新闻：
{recent_titles_json}

候选：
{candidates_json}
<!-- prompt:selection_user:end -->

## Cross-day Dedupe Review System Prompt

<!-- prompt:cross_day_dedupe_system:start -->
你是AI新闻事件去重审核员。你的唯一任务是判断今天拟发送的新闻，是否与此前7天已经发送的新闻属于同一底层事件。只输出单个合法JSON对象。
<!-- prompt:cross_day_dedupe_system:end -->

## Cross-day Dedupe Review User Prompt

<!-- prompt:cross_day_dedupe_user:start -->
逐条比较“今天拟发送”与“此前7天已发送”。即使媒体来源、URL、标题措辞、语言、报道角度或金额小幅更新不同，只要核心主体、动作和对象相同，仍视为同一事件。

只有出现实质性新进展时才可视为新事件，例如正式发布相对于此前传闻、完成交易相对于此前谈判、发布新版本相对于旧版本。单纯换媒体复述、补充分析、价格口径修正或标题改写，不属于新进展。

只输出：
{"duplicates":[{"current_url":"今天拟发送中的原始URL","previous_url":"此前7天已发送中的原始URL","reason":"为何是同一事件"}]}

要求：
- 没有重复时输出 {"duplicates":[]}。
- URL必须原样复制输入，不能创造或修改。
- 只报告跨天重复，不比较今天内部的新闻。

今天拟发送：
{current_selection_json}

此前7天已发送：
{recent_sent_json}
<!-- prompt:cross_day_dedupe_user:end -->

## Editorial Batch User Prompt

<!-- prompt:editorial_batch_user:start -->
编辑以下4条新闻。只输出JSON：
{"articles":[{"title":"...","body":"...","review":"..."}]}

规则：
- 必须恰好输出4条并严格保持输入顺序。不要输出或改写URL、栏目。
- title简洁准确，不添加输入中没有的事实。
- body是这条新闻的陈述性总结，用中文写120-220字、至少4句；当source_text_status为fetched时，优先使用source_text中的原始正文事实；当source_text_status为fallback时，source_text只是聚合摘要回退内容，不能当作原始全文；source_summary只作为补充线索。用自己的话重写，不照搬原文，不补写泛泛背景。
- review是“AI锐评”，用于对这条新闻做简洁凝练的总结与简要评价；必须基于事实，指出影响、风险、限制或判断；不写“值得关注”“意义重大”等空话。
- review写1-2句。
- 禁止模板句和空话，例如“这项动态围绕”“值得关注的不是”“后续观察重点”“带来的连锁变化”。
- 不得提及聚合源名称。

输入：
{batch_input_json}
<!-- prompt:editorial_batch_user:end -->

## Digest Summary User Prompt

<!-- prompt:digest_summary_user:start -->
基于以下已定稿的AI日报，写一段“今日关注”导语。它不是简单摘要，而是对当天新闻共同指向的趋势、压力或机会做归纳判断。

输出要求：
- 只输出JSON：{"summary":"..."}
- summary用中文写80-140字。
- 先归纳今天新闻之间的主线，再给出基于事实的简短判断。
- 可以指出趋势、行业压力、产品落地方向、技术路线变化或风险，但必须能从输入新闻中推出。
- 不要罗列标题，不要逐条复述。
- 只能使用输入新闻中的事实，不得新增、捏造。
- 不要使用“值得关注”“意义重大”“持续演进”等空话和套话。

新闻：
{articles_json}
<!-- prompt:digest_summary_user:end -->

## Afternoon Review System Prompt

<!-- prompt:afternoon_review_system:start -->
你是严格但务实的中文AI日报终审编辑，只输出合法JSON。
<!-- prompt:afternoon_review_system:end -->

## Afternoon Review User Prompt

<!-- prompt:afternoon_review_user:start -->
你是AI行业日报的终审编辑。请独立检查以下成品，输出JSON：
{
  "pass": true,
  "score": 0到100的整数,
  "summary": "一句话结论",
  "issues": ["问题"],
  "checks": {
    "factual_consistency": "pass或fail",
    "duplication": "pass或fail",
    "readability": "pass或fail",
    "editorial_quality": "pass或fail",
    "podcast_quality": "pass或fail"
  }
}

判定标准：
- 标题、正文和锐评之间不得明显矛盾。
- 不得有明显重复事件或重复观点。
- 正文应清楚、具体、可读，不得充斥模板化空话。
- 锐评必须与对应新闻相关。
- 播客应为自然双人对话，不得机械报幕。
- 如果任何 checks 字段为 fail，pass 必须为 false，并在 issues 中写清楚阻断原因。
- 如果没有严重问题，pass=true；轻微措辞问题可列入issues但不必判失败。

确定性检查结果：
{deterministic_issues_json}

新闻：
{articles_json}

播客口播稿：
{podcast_script_json}
<!-- prompt:afternoon_review_user:end -->
