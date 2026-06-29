# AI Daily News Agent Workflow Plan

## Goal

Rebuild the daily-news workflow around one stable agent entrypoint while keeping
delivery actions deterministic.

The target architecture has exactly two GitHub Actions workflows:

```text
GitHub Actions: Morning
  -> python scripts/run_news_agent.py --date YYYY-MM-DD
  -> python scripts/build_content_site.py
  -> python skill/scripts/send_all.py --phase morning

GitHub Actions: Afternoon
  -> download same-day artifacts from gh-pages
  -> validate manifest
  -> python scripts/upload_delivery_artifacts.py
     upload failure is warning-only
  -> python skill/scripts/send_all.py --phase afternoon
```

All other steps are contained inside one of these two workflows. The agent
prepares and reviews structured materials. Workflow scripts handle publishing,
uploads, email, idempotency, and exit-code decisions.

## Out of Scope and Guardrails

This section lists behavior the new agent workflow must not take over. It is
not a rejection of these features; it is the boundary that keeps production
delivery deterministic.

- Do not let the agent directly send email.
- Do not let the agent directly mutate recipient lists or delivery policy.
- Do not rely on hidden long-term agent memory.
- Do not replace deterministic validators with LLM-only review.
- Do not remove the existing pipeline until the new path is proven.

## Agent Runtime

The implementation should be based on DeepAgent.

DeepAgent should provide:

- Agent harness and run lifecycle.
- Skill loading and skill routing.
- Managed memory primitives.
- Tool orchestration.
- Structured task execution.

The project should not reimplement those DeepAgent capabilities unless there is
a clear gap. `scripts/run_news_agent.py` should mainly adapt project-specific
inputs, state files, schemas, validation rules, and artifact paths to DeepAgent.

## One Entry Script

Add:

```text
scripts/run_news_agent.py
```

Default command:

```bash
python scripts/run_news_agent.py --date 2026-06-29
```

Optional commands:

```bash
python scripts/run_news_agent.py --date 2026-06-29 --check-only
python scripts/run_news_agent.py --date 2026-06-29 --force-regenerate
```

The workflow should call only the default command for normal runs.

Internally the script may run multiple stages, but the public interface remains
one command.

## Check-Only Semantics

`--check-only` must not call LLMs, TTS, network news sources, upload APIs, or
SMTP. It only checks manifest and declared local artifacts.

Checks:

- `dist/manifest-YYYY-MM-DD.json` exists.
- Manifest date matches `--date`.
- `manifest.status == "ready"`.
- `manifest.quality.deterministic == "pass"`.
- `manifest.quality.agent_review == "pass"`.
- Manifest-declared artifacts exist.
- Basic artifact sizes are sane.

Exit codes:

```text
0  READY      Materials complete and valid.
10 MISSING    Manifest or required artifact missing.
20 INVALID    Manifest schema invalid, file missing, or size abnormal.
30 FAILED     Manifest says generation/review failed.
40 STALE      Manifest date mismatch or stale output.
50 ERROR      Checker infrastructure error.
```

Workflow use:

```bash
python scripts/run_news_agent.py --date "$DATE" --check-only
STATUS=$?
if [ "$STATUS" -eq 0 ]; then
  echo "Already ready"
else
  python scripts/run_news_agent.py --date "$DATE"
fi
```

## Minimal State File

Only one state file is required for near-term deduplication:

```text
state/recent-news.json
```

Purpose: keep the last 7 days of candidate and selected titles.

Schema:

```json
{
  "window_days": 7,
  "days": {
    "2026-06-29": {
      "candidates": [
        {"title": "OpenAI releases ...", "url": "https://..."}
      ],
      "selected": [
        {"title": "OpenAI releases ...", "url": "https://..."}
      ]
    }
  }
}
```

Rules:

- Agent reads only titles and URLs from the recent window.
- Dedupe is advisory, not a hard global block.
- Similar titles should be inspected for event identity.
- Similar but materially different news must not be dropped.
- The script trims entries older than `window_days`.
- The agent outputs proposed updates; the script validates and writes state.

## Manifest

Every successful or failed run writes:

```text
dist/manifest-YYYY-MM-DD.json
```

Schema outline:

```json
{
  "schema_version": 1,
  "date": "2026-06-29",
  "status": "ready",
  "artifacts": {
    "articles": "dist/articles-2026-06-29.json",
    "html": "dist/daily-news-2026-06-29.html",
    "podcast_script": "dist/podcast-script-2026-06-29.json",
    "podcast_moss_input": "dist/podcast-moss-input-2026-06-29.txt",
    "audio": "dist/daily-news-podcast-2026-06-29.mp3"
  },
  "quality": {
    "deterministic": "pass",
    "agent_review": "pass"
  },
  "repair": {
    "attempts": 0,
    "items": []
  },
  "memory_update": {
    "candidate_count": 0,
    "selected_count": 0
  }
}
```

Status values:

```text
ready
failed
needs_human_review
partial
```

The redundant cron relies on this manifest. If it is already `ready`, it skips
generation.

## Published Artifact Store

GitHub runners are separate VMs. Afternoon cannot read morning `dist/`.

Use `gh-pages` as the cross-workflow artifact store:

```text
gh-pages/
  api/issues/YYYY-MM-DD/
    manifest.json
    articles.json
    podcast-script.json
  html/YYYY-MM-DD.html
  audio/YYYY-MM-DD.mp3
  api/latest.json
```

Morning publishes all artifacts after validation.

Afternoon downloads by date from `gh-pages`, preferably from:

```text
https://dedarek.github.io/ai-daily-news-workflow/api/issues/YYYY-MM-DD/manifest.json
```

Do not rely only on `api/latest.json` for afternoon. `latest.json` is acceptable
as a fallback or summary, but date-specific manifest is the source of truth.

## Morning Workflow

Both morning cron entries run the same command.

```text
cron 1
  -> run_news_agent.py --date DATE
  -> if ready, publish
  -> send admins

cron 2
  -> run_news_agent.py --date DATE
  -> if manifest already ready, skip generation
  -> if missing/failed, regenerate or repair
```

The script decides whether to generate based on manifest status unless
`--force-regenerate` is set.

## Afternoon Workflow

Afternoon must not regenerate content.

Flow:

```text
1. Download date-specific manifest and artifacts from gh-pages.
2. Verify manifest.status == ready.
3. Run independent review and deterministic checks.
4. Run file upload if requested/scheduled.
5. File upload failure is warning only.
6. Send all-recipient email.
7. Email failure is fatal.
8. Write delivery marker only after email succeeds.
```

## Repair and Retry

The script may repair only deterministic or structural failures.

### Auto-repair allowed

Structural failures:

- Invalid JSON output.
- Missing required field.
- Missing artifact.
- Podcast speakers not alternating.
- Manifest schema invalid.

Deterministic quality failures:

- Too few articles.
- Body text too short.
- Banned template phrases.
- Podcast turns out of allowed range.
- `covered_titles` not 5-7 items.
- HTML too small.
- MP3 too small or too large.

Retry limit:

```text
max_repair_attempts = 2
```

### Auto-repair not allowed

Escalate to `needs_human_review`:

- Agent review says factual consistency failed.
- Source facts conflict.
- News appears highly similar but event identity is unclear.
- Important claim lacks enough support for safe automatic rewrite.

Repair log must be written into manifest:

```json
{
  "attempt": 1,
  "reason": "podcast_turns < 20",
  "action": "regenerate_podcast_script",
  "result": "pass"
}
```

## Skill Layout

Restructure skills into a small number of non-overlapping files.

```text
skill/
  SKILL.md
  references/
    news-agent-rules.md
    output-schema.md
    delivery-rules.md

moss-ttsd/
  SKILL.md
  references/
    voice-config.json
```

### `skill/SKILL.md`

Short total entrypoint. It must define required reading order:

1. `skill/references/news-agent-rules.md`
2. `skill/references/output-schema.md`
3. `skill/references/delivery-rules.md`
4. `moss-ttsd/SKILL.md`
5. `moss-ttsd/references/voice-config.json`

It must not contain large historical logs or implementation details.

### `news-agent-rules.md`

Owns:

- News source policy.
- Candidate extraction.
- 7-day title dedupe policy.
- Selection rules.
- Article writing rules.
- Podcast script rules.
- Repair/retry rules.

Does not own SMTP, upload, recipients, or TTS voice config.

### `output-schema.md`

Owns schema for:

- `articles.json`
- `podcast-script.json`
- `manifest.json`
- `recent-news.json`

### `delivery-rules.md`

Owns:

- Morning sends `admins`.
- Afternoon sends `all`.
- Recipients come only from JSON config.
- Upload failure is warning.
- Email failure is fatal.

### `moss-ttsd/SKILL.md`

Owns:

- MOSS model.
- `[S1]` / `[S2]` text format.
- Audio constraints.
- Reference transcript requirements.

### `moss-ttsd/references/voice-config.json`

Owns:

```json
{
  "model": "fnlp/MOSS-TTSD-v0.5",
  "voices": {
    "S1": {
      "name": "老陈",
      "audio": "moss-ttsd/references/voice_laochen_s1.wav",
      "transcript_env": "MOSS_TTS_S1_REFERENCE_TEXT"
    },
    "S2": {
      "name": "小满",
      "audio": "moss-ttsd/references/voice_anna_s2.mp3",
      "transcript_env": "MOSS_TTS_S2_REFERENCE_TEXT"
    }
  }
}
```

## Migration Plan

### Phase 1: Add Agent Entrypoint Without Removing Old Pipeline

- Add `scripts/run_news_agent.py`.
- Add `state/recent-news.json`.
- Add manifest generation.
- Reuse existing collection, TTS, validation utilities where practical.
- Keep `run_live_pipeline.py` as fallback.

### Phase 2: Publish Manifest and Update Afternoon

- Update `build_content_site.py` to publish date-specific manifest.
- Update `prepare_review_delivery.py` to download by manifest.
- Keep `latest.json` as summary only.

### Phase 3: Skill Cleanup

- Replace oversized `skill/SKILL.md` with a routing entrypoint.
- Add focused reference docs.
- Update `moss-ttsd` to match current MOSS reference-audio path.

### Phase 4: Workflow Switch

- Morning workflow calls `run_news_agent.py`.
- Redundant cron relies on manifest skip.
- Afternoon consumes published manifest and sends.

### Phase 5: Remove or Demote Legacy Paths

- After several successful runs, mark old scripts as legacy or remove unused
  paths.

## Approval Checklist

Before implementation, confirm:

- One public agent command is acceptable.
- `state/recent-news.json` with 7-day title/url memory is enough.
- `gh-pages` is acceptable as cross-workflow artifact store.
- Afternoon never regenerates content.
- Upload failure remains warning-only.
- Email failure remains fatal.
