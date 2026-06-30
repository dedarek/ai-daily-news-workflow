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
- 参考“最近7天记录”避免重复选择同一事件，尤其避免重复已选新闻。
- 只把“同一事件/同一发布/同一研究结果”的新闻视为重复；相似主题但事件不同的新闻不能错过。
- 最近记录中的每条都包含date/title/summary/url；比较时优先用title+summary判断事件是否相同。

最近7天记录：
{recent_titles_json}

候选：
{candidates_json}
<!-- prompt:selection_user:end -->

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
- 如果没有严重问题，pass=true；轻微措辞问题可列入issues但不必判失败。

确定性检查结果：
{deterministic_issues_json}

新闻：
{articles_json}

播客口播稿：
{podcast_script_json}
<!-- prompt:afternoon_review_user:end -->
