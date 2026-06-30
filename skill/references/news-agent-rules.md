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
- Read only titles and URLs from `state/recent-news.json` for the last seven days.
- Use the recent state as an advisory dedupe signal, not a hard global block.
- If two titles look similar, compare event identity before dropping either.
- Similar but materially different events must not be dropped.
- Candidate and selected titles must be written back through the supervisor state update.

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

Automatic repair is allowed only for deterministic or structural failures:

- Invalid JSON.
- Missing required fields.
- Missing artifacts.
- Speaker alternation failure.
- Too few selected articles.
- Body text too short.
- Podcast turn count outside the allowed range.
- MP3 size outside the allowed range.
- Manifest schema invalid.

Do not auto-repair factual conflicts. Mark the run as `needs_human_review` if:

- Facts conflict across sources.
- The Agent cannot determine whether similar news items are the same event.
- A major claim lacks enough support.
- The review finds factual consistency failure.

Maximum automatic repair attempts: `2`.
