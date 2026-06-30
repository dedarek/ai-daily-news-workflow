---
name: skill
description: >-
  AI Daily News production workflow. Use when preparing, validating, publishing,
  reviewing, or delivering the Chinese daily AI news issue, including articles,
  HTML, podcast script, manifest, recipient phases, and delivery rules.
---

# AI Daily News Skill

This is the root skill for the daily AI news workflow.

The Agent must use this skill for:

- Morning material preparation for the admin review email.
- Afternoon validation before all-recipient delivery.
- Manifest and artifact validation.
- Seven-day news title deduplication.
- Podcast script requirements.
- Delivery phase rules.

## Required Reading Order

When this skill is activated, read these files in order:

1. `references/news-agent-rules.md`
2. `references/output-schema.md`
3. `references/news-prompts.md`
4. `references/podcast-prompts.md`
5. `references/delivery-rules.md`
6. `../moss-ttsd/SKILL.md`
7. `../moss-ttsd/references/voice-config.json`

Do not scan historical logs unless a human explicitly asks for debugging a
specific historical date.

## Boundaries

- The Agent prepares and validates materials.
- The Agent may propose repairs for structural or deterministic failures.
- The Agent must not send email directly.
- The Agent must not upload files directly.
- The Agent must not mutate `references/recipients.json`.
- The Agent must not mutate `references/send-email-config.json`.
- The Agent must not mutate `references/send-file-config.json`.
- The Agent must not write delivery markers.

Delivery, upload, idempotency markers, and SMTP are handled by deterministic
scripts outside the Agent.
