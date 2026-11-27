"""Allowlisted operational metadata for the public digest."""
import re

DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
STAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?$')
TTS = {'text-only', 'siliconflow-moss-reference-live', 'video-api-audio-video'}
NUMS = ('article_count', 'candidate_count', 'podcast_turns', 'voice_turns',
        'html_bytes', 'podcast_bytes', 'video_bytes', 'podcast_duration_seconds')
PUBLIC_ORIGIN = 'https://dedarek.github.io/ai-daily-news-workflow/'
LINKS = {
    'articles': 'articles.json', 'candidate_articles': 'candidate-news.json',
    'podcast_script': 'podcast-script.json', 'podcast_script_text': 'podcast-script.txt',
    'podcast_dialogue_text': 'podcast-dialogue/{date}.txt',
    'podcast_moss_input': 'podcast-moss-input.txt', 'voice': 'voice.json',
    'voice_timeline': 'voice/{date}.json', 'html': 'html/{date}.html',
    'audio': 'audio/{date}.mp3', 'video': 'video/{date}.mp4',
    'index': 'index.json', 'manifest': 'manifest.json', 'pipeline_report': 'pipeline-report.json',
}


def enum(value, allowed):
    return value if isinstance(value, str) and value in allowed else None


def match(value, pattern):
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def public_report(report, date):
    out = {'issue_date': date, 'content_date': match(report.get('content_date'), DATE),
           'tts_mode': enum(report.get('tts_mode'), TTS)}
    out.update({key: report[key] for key in NUMS if type(report.get(key)) in (int, float)})
    summary = report.get('digest_summary')
    if isinstance(summary, str) and len(summary) <= 12000 and not re.search(
            r'@|https?://|\b(?:token|password|base_url)\s*[:=]', summary, re.I):
        out['digest_summary'] = summary
    return out


def public_url(value, artifact, date):
    template = LINKS[artifact]
    suffix = template.format(date=date) if '{date}' in template else f'api/issues/{date}/{template}'
    return value if value == PUBLIC_ORIGIN + suffix else None


def public_index(issue):
    date = match(issue.get('issue_date'), DATE)
    if not date:
        raise ValueError('Invalid public issue date')
    fields = {'schema_version': 1, 'issue_date': date,
              'content_date': match(issue.get('content_date'), DATE),
              'published_at': match(issue.get('published_at'), STAMP),
              'tts_mode': enum(issue.get('tts_mode'), TTS)}
    fields.update({key: issue[key] for key in ('article_count', 'podcast_turns')
                   if type(issue.get(key)) is int})
    for k in LINKS:
        if k not in {'index', 'pipeline_report'}:
            fields[k + '_url'] = public_url(issue.get(k + '_url'), k, date)
    if not fields['html_url']:
        raise ValueError('Public issue must have its canonical HTML URL')
    return fields


def public_manifest(manifest, report, artifacts, date):
    quality = manifest.get('quality') or {}
    result = {'schema_version': 1, 'date': date,
              'status': enum(manifest.get('status'), {'ready', 'partial', 'failed'}),
              'created_at': match(manifest.get('created_at'), STAMP),
              'quality': {key: enum(quality.get(key), {'pass', 'fail', 'not_run'})
                          for key in ('deterministic', 'agent_review')},
              'pipeline_report': public_report(report, date),
              'published_artifacts': {k: public_url(artifacts.get(k), k, date)
                                      for k in artifacts if k in LINKS}}
    if result['status'] != 'ready' or not result['published_artifacts'].get('html'):
        raise ValueError('Invalid public manifest')
    if result['pipeline_report']['tts_mode'] != 'text-only' and not result['published_artifacts'].get('audio'):
        raise ValueError('Missing public audio')
    return result
