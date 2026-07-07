# Output Schema

## Artifact Names

The canonical output directory is `dist/`.

Required same-day files:

- `dist/candidate-news-YYYY-MM-DD.json`
- `dist/articles-YYYY-MM-DD.json`
- `dist/daily-news-YYYY-MM-DD.html`
- `dist/podcast-script-YYYY-MM-DD.json`
- `dist/podcast-script-YYYY-MM-DD.txt`
- `dist/podcast-moss-input-YYYY-MM-DD.txt`
- `dist/daily-news-podcast-YYYY-MM-DD.mp3`
- `dist/daily-news-video-YYYY-MM-DD.mp4`
- `dist/pipeline-report-YYYY-MM-DD.json`
- `dist/manifest-YYYY-MM-DD.json`

Legacy compatibility files may also exist:

- `dist/news-data-YYYY-MM-DD.json`
- `dist/ai-daily-news-html-YYYY-MM-DD.html`
- `dist/ai-daily-news-podcast-YYYY-MM-DD.mp3`
- `dist/ai-daily-news-video-YYYY-MM-DD.mp4`

## `articles-YYYY-MM-DD.json`

Array of article objects:

```json
{
  "title": "string",
  "summary": "string",
  "url": "https://...",
  "section": "string",
  "review": "string"
}
```

## `podcast-script-YYYY-MM-DD.json`

```json
{
  "issue_date": "YYYY-MM-DD",
  "speakers": {
    "S1": {"name": "老陈", "role": "资深AI从业者"},
    "S2": {"name": "小满", "role": "产品与应用视角"}
  },
  "dialogue": [
    {"speaker": "S1", "text": "string"},
    {"speaker": "S2", "text": "string"}
  ]
}
```

## `voice-YYYY-MM-DD.json`

```json
{
  "title": "AI热点新闻",
  "date": "YYYY-MM-DD",
  "audio": "dist/daily-news-podcast-YYYY-MM-DD.mp3",
  "video": "dist/daily-news-video-YYYY-MM-DD.mp4",
  "duration": 123.45,
  "turns": [
    {
      "index": 0,
      "roleLabel": "S1",
      "text": "string",
      "start": 0.0,
      "end": 4.2
    }
  ]
}
```

## `manifest-YYYY-MM-DD.json`

```json
{
  "schema_version": 1,
  "date": "YYYY-MM-DD",
  "status": "ready",
  "created_at": "ISO-8601",
  "artifacts": {
    "candidate_articles": "dist/candidate-news-YYYY-MM-DD.json",
    "articles": "dist/articles-YYYY-MM-DD.json",
    "html": "dist/daily-news-YYYY-MM-DD.html",
    "podcast_script": "dist/podcast-script-YYYY-MM-DD.json",
    "podcast_script_text": "dist/podcast-script-YYYY-MM-DD.txt",
    "podcast_moss_input": "dist/podcast-moss-input-YYYY-MM-DD.txt",
    "audio": "dist/daily-news-podcast-YYYY-MM-DD.mp3",
    "video": "dist/daily-news-video-YYYY-MM-DD.mp4",
    "pipeline_report": "dist/pipeline-report-YYYY-MM-DD.json"
  },
  "quality": {
    "deterministic": "pass",
    "agent_review": "pass",
    "issues": []
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

When published to GitHub Pages, the raw podcast dialogue text must also be
available at:

```text
https://dedarek.github.io/ai-daily-news-workflow/podcast-dialogue/YYYY-MM-DD.txt
```

The generated video must be published at:

```text
https://dedarek.github.io/ai-daily-news-workflow/video/YYYY-MM-DD.mp4
```

Allowed manifest status values:

- `ready`
- `failed`
- `needs_human_review`
- `partial`

## `state/recent-news.json`

```json
{
  "window_days": 7,
  "days": {
    "YYYY-MM-DD": {
      "candidates": [{"title": "string", "url": "string"}],
      "selected": [{"title": "string", "url": "string"}]
    }
  }
}
```

Only titles and URLs belong in this state file.
