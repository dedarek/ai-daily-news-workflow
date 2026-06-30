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
- 选择要兼顾重要性、信息密度和话题结构，不要只选同一类新闻。
- 参考“最近7天记录”避免重复选择同一事件；相似主题但事件不同的新闻不能错过。
- 最近记录包含date/title/summary/url，判断重复时重点比较事件本身，而不是只看标题相似度。

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
- body是给读者看的陈述性总结，要信息丰富、清楚具体，用自己的话讲清发生了什么、关键细节、可能影响；不要照搬原文，不要补写输入里没有的事实。
- 当source_text_status为fetched时，优先使用source_text中的原始正文事实；当source_text_status为fallback时，source_text只是聚合摘要回退内容，不能当作原始全文。
- review是“AI锐评”，要短而有判断，基于事实指出影响、风险、限制或机会；避免空话、模板句和与body重复。
- 语言可以有编辑风格，但不要夸张，不要用“值得关注”“意义重大”等泛泛表述。
- 不得提及聚合源名称。

输入：
{batch_input_json}
<!-- prompt:editorial_batch_user:end -->

## Digest Summary User Prompt

<!-- prompt:digest_summary_user:start -->
基于以下已定稿的AI日报，写一段“今日关注”导语。

输出要求：
- 只输出JSON：{"summary":"..."}
- summary用中文总结，60-110字。
- 不要罗列标题。
- 要概括今天新闻之间的主线，给读者一个进入全篇的判断。
- 内容要具体、有信息量，可以点出趋势、张力或共同变化。
- 只能使用输入新闻中的事实，不得新增、捏造。
- 不要使用空话和套话。

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
- 正文应清楚、具体、可读，有足够信息量，不应只是几句泛泛概括。
- 锐评必须与对应新闻相关，并体现判断。
- 播客应为自然双人讨论，有解释、有连接、有判断，不得机械报幕。
- 如果没有严重问题，pass=true；轻微措辞问题可列入issues但不必判失败。

确定性检查结果：
{deterministic_issues_json}

新闻：
{articles_json}

播客口播稿：
{podcast_script_json}
<!-- prompt:afternoon_review_user:end -->
