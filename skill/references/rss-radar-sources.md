# RSS Radar Sources from HN Popular Blogs 2025

Source: https://gist.github.com/emschwartz/e6d2bf860ccc367fe37ff953ba6de66b

This file is a first-pass classification of the 92 OPML entries into categories useful for `ai-daily-news`.

## How to use this file

- **Direct candidates**: sources with frequent AI / LLM / agent / ML systems relevance. These can be monitored more closely for direct candidate articles, but still require original timestamp validation.
- **Radar candidates**: high-quality engineering or analysis blogs that may surface AI-relevant themes, infrastructure shifts, or strong essays. Use for discovery first.
- **Low priority for current daily**: good blogs, but too broad or too weakly aligned with the current AI daily scope.

## A. Direct candidates for AI daily monitoring

These are the most promising entries from the OPML for current AI daily use:

- simonwillison.net
  - Why: very strong overlap with LLMs, tooling, agents, prompt interfaces, evals, and AI engineering.
- garymarcus.substack.com
  - Why: AI commentary and model critique; good for industry debate and perspective.
- entropicthoughts.com
  - Why: often relevant to AI, research, and analytical technology essays.
- construction-physics.com
  - Why: useful for longer-form industry and technology trend framing; sometimes relevant to AI infrastructure and macro context.
- joanwestenberg.com
  - Why: often touches AI/product/tech trend writing; use as filtered radar.

## B. Radar candidates worth keeping in the discovery layer

These do not map cleanly to daily AI news every day, but are valuable as lower-noise technical radar:

- seangoedecke.com
- mitchellh.com
- lucumr.pocoo.org
- matklad.github.io
- xania.org
- skyfall.dev
- overreacted.io
- xeiaso.net
- righto.com
- johndcook.com
- hillelwayne (buttondown)
- rachelbythebay.com
- jeffgeerling.com
- nesbitt.io
- maurycyz.com
- evanhahn.com
- susam.net
- gilesthomas.com

Use these primarily to discover:
- new technical workflows
- systems and infra ideas
- strong essays relevant to AI engineering culture
- adjacent topics that deserve follow-up to an original AI source

## C. Low-priority for current AI daily scope

These may still be excellent blogs, but they are not strong fits for the current “daily AI hotspot news” product unless a specific article is unusually relevant:

- krebsonsecurity.com
- daringfireball.net
- antirez.com
- idiallo.com
- pluralistic.net
- shkspr.mobi
- lcamtuf.substack.com
- utcc.utoronto.ca/~cks
- devblogs.microsoft.com/oldnewthing
- timsh.org
- derekthompson.org
- terriblesoftware.org
- rakhim.exotext.com
- micahflee.com
- tedium.co

These are better suited for:
- background reading
- broader tech analysis
- occasional one-off inclusion if a post is directly AI-relevant

## Recommended policy for this OPML set

1. Do **not** import all 92 directly into the formal source backbone.
2. Create a **radar layer** from this OPML set.
3. Promote only a small subset into higher-priority monitoring.
4. Continue to require:
   - original article timestamp validation
   - AI relevance validation
   - cross-day deduplication against recent sent issues

## Next refinement tasks

- Review all 92 entries and expand this classification from partial to full coverage.
- Add notes for each feed on:
  - AI relevance score
  - posting frequency
  - timestamp extractability
  - whether it tends to produce original reporting, essays, or commentary
- Select a final shortlist for the radar layer (target: 15-25 feeds).
