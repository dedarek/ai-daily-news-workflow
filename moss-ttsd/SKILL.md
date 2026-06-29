---
name: moss-ttsd
description: >-
  Generate a two-speaker Chinese podcast audio file with SiliconFlow
  MOSS-TTSD reference-audio mode. Use only the approved S1/S2 reference voices
  from this project.
---

# MOSS-TTSD Skill

This skill owns podcast audio synthesis rules for AI Daily News.

## Required Voice Config

Read `references/voice-config.json` before generating or validating audio.

The only allowed voices are:

- `S1`: `moss-ttsd/references/voice_laochen_s1.wav`
- `S2`: `moss-ttsd/references/voice_anna_s2.mp3`

Do not use built-in voice IDs.
Do not use `alex`, `anna`, or MOSI voice IDs.
Do not substitute other reference files.

## Model

Use:

```text
fnlp/MOSS-TTSD-v0.5
```

Endpoint:

```text
POST https://api.siliconflow.cn/v1/audio/speech
```

The production script sends both reference audio files in the `references`
payload and uses `response_format=mp3`.

## Dialogue Input Format

The TTS input must be one continuous string:

```text
[S1]老陈的一句话[S2]小满的回应[S1]继续讨论
```

Rules:

- Only `S1` and `S2` are allowed.
- Speakers must alternate.
- Use one synthesis call for the full conversation.
- Do not synthesize turn-by-turn and concatenate.
- Do not generate fallback/sample audio if synthesis fails.

## Required Outputs

For `YYYY-MM-DD`:

- `dist/podcast-script-YYYY-MM-DD.json`
- `dist/podcast-script-YYYY-MM-DD.txt`
- `dist/podcast-moss-input-YYYY-MM-DD.txt`
- `dist/daily-news-podcast-YYYY-MM-DD.mp3`

The pipeline report and manifest must record:

- `tts_mode = siliconflow-moss-reference-live`
- `tts_model = fnlp/MOSS-TTSD-v0.5`
- both reference file paths
