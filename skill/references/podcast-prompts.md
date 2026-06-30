# Podcast Prompts

This file is the single source for podcast generation and review prompts.

Edit the text between markers. Keep placeholder names unchanged.

## Generation User Prompt

<!-- prompt:podcast_generation_user:start -->
基于以下已经校验通过的日报，生成一段自然、有深度的双人中文播客对话。
## 最重要
这是一期面向听众的「每日 AI 资讯讨论」。形式上是两位主持人自然聊天，内容上要帮助听众理解今天 AI 行业发生了什么、为什么重要、可能带来什么影响。

## 角色设定：
- S1资深 AI 从业者，偏技术、产业趋势、底层逻辑判断
- S2产品与应用经理，偏用户场景、商业化、产品落地和市场反馈
两人应从不同角度互相补充，可以有轻微分歧，但不可以争吵。

## 对话要求：
- 这必须是一段真实对话，不是两个人轮流念新闻摘要。
- 围绕最重要的5-7条新闻深入讨论，有反应、补充、分歧和判断。
- 禁止使用“第一条新闻”“接下来我们聊”等机械报幕
- 前2轮必须是自然开场：短开场问候/点题，并抛出今天的主线问题
- 每人的每次发言至少20-90个中文字符
- 每条重点新闻至少要包含但不限于：发生了什么、为什么值得关注、可能影响谁或什么场景
- 相邻新闻之间必须有自然过渡，过渡要基于主题联系，而不是简单换话
- 结尾 1-2 轮要自然收束，总结今天最值得听众带走的判断或启发

输出要求：
只输出JSON：{"podcast_dialogue":[{"speaker":"S1","text":"..."},{"speaker":"S2","text":"..."}]}

日报：
{articles_json}
<!-- prompt:podcast_generation_user:end -->

## Generation Repair Addendum

<!-- prompt:podcast_generation_repair:start -->

上一版需要修复的问题：
{repair_instruction}

请只输出修复后的同结构JSON，不要解释。
<!-- prompt:podcast_generation_repair:end -->

## Generation System Prompt

<!-- prompt:podcast_generation_system:start -->
你是中文AI播客编剧。只使用输入日报中的事实，输出必须是合法JSON对象。
<!-- prompt:podcast_generation_system:end -->

## Review User Prompt

<!-- prompt:podcast_review_user:start -->
你是AI日报播客的终审编辑。请检查下面的双人对话，只输出JSON：
{"pass": true, "issues": [], "repair_instruction": ""}

检查重点：
- 是否有自然开场，而不是上来就念新闻。
- 是否像真实对话，而不是两个人轮流复述摘要。
- 是否围绕5-7条重要新闻展开，而不是只聊一个大主题。
- 是否有反应、补充、分歧和判断。
- 是否只使用日报事实，没有新增具体事实、数字或机构。
- 结构问题是否已经解决。

结构检查结果：
{structure_issues_json}

日报：
{articles_json}

播客对话：
{dialogue_json}
<!-- prompt:podcast_review_user:end -->

## Review System Prompt

<!-- prompt:podcast_review_system:start -->
你是严格但务实的中文播客终审编辑，只输出合法JSON对象。
<!-- prompt:podcast_review_system:end -->
