# News Agent Rules

## Objective

Prepare one Chinese AI daily-news issue for the given `YYYY-MM-DD`.

The issue must include:

- 12 selected AI news articles for the HTML/email digest.
- A natural two-speaker podcast script covering 5-7 of those articles.
- A MOSS-TTSD input text file.
- An MP3 generated only from the approved two reference voices.
- A manifest describing all generated artifacts and validation status.

## Source and Selection Rules

- Prefer current, concrete AI product, research, open-source, policy, and industry news.
- Keep the selection event-based. Do not include multiple articles about the same event.
- Read only date, title, summary, and URL from `state/recent-news.json` for the last seven days.
- Use the recent state as an advisory dedupe signal, not a hard global block.
- If two records look similar, compare event identity from title and summary before dropping either.
- Similar but materially different events must not be dropped.
- Candidate and selected date/title/summary/URL records must be written back through the supervisor state update.
- Memory is persisted across days on the `gh-pages` branch. Before generation the supervisor restores `state/recent-news.json` from the published site (`restore_memory_from_site`); after updating it, the supervisor writes it back to the published site (`sync_memory_to_site`) so the publish step commits it. This closed loop is what makes the seven-day dedupe actually effective — without it the memory would stay empty every run.

## Article Rules

- Use Chinese.
- Each article needs a clear title, a factual body, a source URL, a section, and a short review.
- Bodies should be specific and avoid generic filler.
- Do not mention aggregation-source names in the user-facing HTML.
- Do not invent source URLs or facts.

## Podcast Rules

- Select 5-7 news items from the final article list.
- Write one continuous two-speaker discussion, not a bulletin list.
- Speakers:
  - `S1`: 老陈, senior AI practitioner perspective.
  - `S2`: 小满, product and application perspective.
- Use 20-28 turns.
- Speakers must alternate strictly: `S1`, `S2`, `S1`, `S2`, ...
- Each turn should be 35-110 Chinese characters.
- The first two turns must be a natural opening: S1 greets or frames the day, S2 responds and raises the main question.
- The conversation must not start directly with `company + announced/released/launched`.
- The conversation must include questions, pushback, transitions, and cross-topic links.
- Avoid stiff phrases such as `第一条新闻`, `第二条新闻`, `接下来我们聊`, `下面来看`.

## Repair and Retry

Podcast dialogue quality is judged by the **LLM Harness** (the review step), not by mechanical code rules.

The repair loop follows Deep Agent Loop principles (带记忆的持续优化，而非机械重试):

1. **Generate** — Deep Agent produces the dialogue.
2. **Harness** — LLM reviewer evaluates quality holistically: natural opening, real discussion depth, turn count, turn length, use of facts, interaction between speakers.
3. **Repair with accumulated trajectory** — If Harness says `pass: false`, the *entire history* of past attempts and their issues is fed back into the next generation call. The agent iterates with memory and must not repeat earlier mistakes, rather than reacting to a single isolated instruction.
4. **Keep the best** — The loop always tracks the *best* attempt so far (fewest structural + review issues), not just the latest one.
5. **Converge, don't spin** — The attempt budget (currently 5) is only a guardrail. The loop stops early when it stalls (no improvement across two consecutive rounds); it is not a fixed mechanical count.
6. **Honest fallback** — If no attempt passes the Harness, the loop returns the *best* attempt (not the last) and marks `harness.final_pass = false`, `harness.loop_exhausted = true` in the manifest metadata (`llm.call_details.podcast_harness`) so downstream review and humans can see it. The pipeline does not crash and does not pretend success.

Code-level hard blocks are reserved only for truly broken output:

- Invalid JSON.
- Empty dialogue.
- Wrong speaker field values.
- Missing required artifacts.
- MP3 size outside the allowed range.
- Manifest schema invalid.

Do not auto-repair factual conflicts. Mark the run as `needs_human_review` if:

- Facts conflict across sources.
- The Agent cannot determine whether similar news items are the same event.
- A major claim lacks enough support.
- The review finds factual consistency failure.
