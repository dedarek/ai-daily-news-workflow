#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / 'skill'
VOICE_SAMPLE = REPO_ROOT / 'moss-ttsd' / 'references' / 'voice_anna_s2.mp3'
SOURCE_ROOT = 'https://hex2077.dev/docs'
FORBIDDEN_URL_PARTS = ('hex2077.dev', 'aibase.com', 'hubtoday', 'wappoc_appmsgcaptcha')
SECTION_ORDER = ['🔥 今日焦点', '🚀 产品发布', '💼 行业动态', '💡 前沿研究', '🔓 开源热榜', '🤖 Agent & 工具']


@dataclass
class Article:
    title: str
    summary: str
    url: str
    section: str
    review: str = ''


class DailyPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.heading_depth = 0
        self.heading_text: list[str] = []
        self.current_heading = ''
        self.in_li = False
        self.li_depth = 0
        self.li_text: list[str] = []
        self.li_links: list[str] = []
        self.li_strong_depth = 0
        self.li_title: list[str] = []
        self.li_title_complete = False
        self.items: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in ('h2', 'h3'):
            self.heading_depth += 1
            self.heading_text = []
        if tag == 'li' and not self.in_li:
            self.in_li = True
            self.li_depth = 1
            self.li_text = []
            self.li_links = []
            self.li_title = []
            self.li_title_complete = False
        elif self.in_li:
            if tag == 'li':
                self.li_depth += 1
            if tag == 'strong':
                self.li_strong_depth += 1
            if tag == 'a':
                href = attrs_dict.get('href') or ''
                if href.startswith(('http://', 'https://')):
                    self.li_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in ('h2', 'h3') and self.heading_depth:
            self.current_heading = clean_text(''.join(self.heading_text))
            self.heading_depth -= 1
        if not self.in_li:
            return
        if tag == 'strong' and self.li_strong_depth:
            self.li_strong_depth -= 1
            if self.li_title:
                self.li_title_complete = True
        if tag == 'li':
            self.li_depth -= 1
            if self.li_depth == 0:
                title = clean_text(''.join(self.li_title))
                body = clean_text(''.join(self.li_text))
                url = next((u for u in self.li_links if valid_article_url(u)), '')
                if title and body and url:
                    self.items.append((self.current_heading, title, body))
                    self.items[-1] = (self.current_heading, title, f'{body}\n{url}')
                self.in_li = False

    def handle_data(self, data: str) -> None:
        if self.heading_depth:
            self.heading_text.append(data)
        if self.in_li:
            self.li_text.append(data)
            if self.li_strong_depth and not self.li_title_complete:
                self.li_title.append(data)


def clean_text(text: str) -> str:
    text = re.sub(r'\(AI资讯\)', '', text, flags=re.I)
    text = text.replace('🚀', '').replace('(✧∀✧)', '').replace('⭐', '')
    return re.sub(r'\s+', ' ', text).strip()


def valid_article_url(url: str) -> bool:
    lower = url.lower()
    if any(part in lower for part in FORBIDDEN_URL_PARTS):
        return False
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc) and parsed.path not in ('', '/')


def section_for(source_heading: str, index: int) -> str:
    heading = source_heading.lower()
    if index == 0:
        return '🔥 今日焦点'
    if '开源' in source_heading:
        return '🔓 开源热榜'
    if '研究' in source_heading:
        return '💡 前沿研究'
    if any(word in heading for word in ('agent', '工具', '社媒')):
        return '🤖 Agent & 工具'
    if any(word in source_heading for word in ('产品', '功能', '发布')):
        return '🚀 产品发布'
    return '💼 行业动态'


def expand_summary(title: str, raw: str) -> str:
    raw = clean_text(raw)
    raw = raw.removeprefix(title).lstrip('。 ')
    sentences = [s.strip() for s in re.split(r'(?<=[。！？])', raw) if s.strip()]
    base = ''.join(sentences[:4]).strip()
    if not base.endswith(('。', '！', '？')):
        base += '。'
    context = (
        f'这项动态围绕“{title.rstrip("。")}”展开，值得关注的不是单一功能，而是它对产品能力、'
        '开发流程和实际应用门槛带来的连锁变化。后续观察重点包括公开能力是否按计划落地、'
        '真实用户反馈以及同类产品是否快速跟进。'
    )
    result = base + context
    return result[:420]


def fetch_latest(issue_date: str) -> tuple[str, str, str]:
    start = datetime.strptime(issue_date, '%Y-%m-%d').date()
    errors: list[str] = []
    for offset in range(4):
        candidate = start - timedelta(days=offset)
        candidate_str = candidate.isoformat()
        url = f'{SOURCE_ROOT}/{candidate_str[:7]}/{candidate_str}/'
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 AI-Daily-News-Workflow/1.0'})
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode('utf-8', errors='replace')
            if len(raw) > 10_000:
                return candidate_str, url, raw
        except Exception as exc:
            errors.append(f'{candidate_str}: {type(exc).__name__}')
    raise RuntimeError('No daily source page available: ' + ', '.join(errors))


def parse_articles(raw_html: str, limit: int = 15) -> list[Article]:
    parser = DailyPageParser()
    parser.feed(raw_html)
    articles: list[Article] = []
    seen: set[tuple[str, str]] = set()
    for heading, title, body_and_url in parser.items:
        body, url = body_and_url.rsplit('\n', 1)
        key = (title.lower(), url)
        if key in seen or not valid_article_url(url):
            continue
        if any(word in heading for word in ('多渠道', '摘要')):
            continue
        seen.add(key)
        articles.append(
            Article(
                title=title.rstrip('。'),
                summary=expand_summary(title, body),
                url=url,
                section=section_for(heading, len(articles)),
            )
        )
        if len(articles) >= limit:
            break
    if len(articles) < 8:
        raise RuntimeError(f'Only {len(articles)} valid live articles were parsed')
    return articles


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end <= start:
        raise RuntimeError('LLM response did not contain a JSON object')
    return json.loads(text[start:end + 1])


def call_deepseek(candidate_articles: list[Article], api_key: str) -> tuple[list[Article], list[dict[str, str]], dict]:
    endpoint = os.environ.get('OPENCODE_GO_BASE_URL', 'https://opencode.ai/zen/go/v1').rstrip('/')
    model = os.environ.get('OPENCODE_GO_MODEL', 'deepseek-v4-pro')
    candidates = [
        {'title': item.title, 'source_summary': item.summary, 'url': item.url, 'suggested_section': item.section}
        for item in candidate_articles
    ]
    system_prompt = (
        '你是中文AI行业日报主编。只使用输入候选中的事实和URL，不得编造事实、数字、机构、'
        '模型能力或链接。输出必须是单个合法JSON对象，不要Markdown。'
    )
    user_prompt = f'''
请编辑以下候选新闻，输出：
1. articles：保留 12-15 条，按事件去重；每项字段为 title、body、section、review、url。
2. podcast_dialogue：12-18轮自然双人对话，每项字段 speaker（S1或S2）与 text。

严格规则：
- url 必须原样取自候选，不得修改或创造。
- body 用中文写 120-220 字，至少4句，只能基于 source_summary 已给出的事实；信息不足时解释技术或行业背景，
  但不得新增无法验证的具体数字。
- section 只能是：{json.dumps(SECTION_ORDER, ensure_ascii=False)}。
- 第一条 section 必须是“🔥 今日焦点”，且仅一条。
- review 1-2句，有明确判断但必须基于事实，不写空洞套话。
- podcast_dialogue 围绕最重要的5-7条新闻展开，S1是资深AI从业者，S2是产品视角；
  禁止“第一条新闻”“接下来我们聊”，每轮20-90字。
- 不得在任何正文、锐评或播客中提及聚合源名称。

输出JSON结构：
{{
  "articles": [
    {{"title":"...", "body":"...", "section":"...", "review":"...", "url":"..."}}
  ],
  "podcast_dialogue": [
    {{"speaker":"S1","text":"..."}}
  ]
}}

候选数据：
{json.dumps(candidates, ensure_ascii=False)}
'''.strip()
    payload = json.dumps({
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.35,
        'max_tokens': 9000,
    }).encode('utf-8')
    request = Request(
        f'{endpoint}/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'ai-daily-news-workflow/1.0',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=240) as response:
            response_data = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        error_body = exc.read().decode('utf-8', errors='replace')[:1000]
        raise RuntimeError(f'OpenCode Go HTTP {exc.code}: {error_body}') from exc
    content = response_data['choices'][0]['message']['content']
    result = extract_json_object(content)
    allowed_urls = {item.url for item in candidate_articles}
    articles: list[Article] = []
    seen_urls: set[str] = set()
    for item in result.get('articles', []):
        url = str(item.get('url', '')).strip()
        if url not in allowed_urls or url in seen_urls:
            continue
        article = Article(
            title=clean_text(str(item.get('title', ''))),
            summary=clean_text(str(item.get('body', ''))),
            url=url,
            section=str(item.get('section', '')).strip(),
            review=clean_text(str(item.get('review', ''))),
        )
        if (
            article.title
            and len(article.summary) >= 120
            and article.section in SECTION_ORDER
            and article.review
        ):
            articles.append(article)
            seen_urls.add(url)
    if not 12 <= len(articles) <= 15:
        raise RuntimeError(f'LLM returned {len(articles)} valid articles; expected 12-15')
    focus_count = sum(item.section == '🔥 今日焦点' for item in articles)
    if articles[0].section != '🔥 今日焦点' or focus_count != 1:
        raise RuntimeError(f'LLM focus-section validation failed: first={articles[0].section}, count={focus_count}')

    dialogue: list[dict[str, str]] = []
    for item in result.get('podcast_dialogue', []):
        speaker = str(item.get('speaker', '')).strip()
        text = clean_text(str(item.get('text', '')))
        if speaker in ('S1', 'S2') and 20 <= len(text) <= 140:
            dialogue.append({'speaker': speaker, 'text': text})
    if not 12 <= len(dialogue) <= 18:
        raise RuntimeError(f'LLM returned {len(dialogue)} valid podcast turns; expected 12-18')
    usage = response_data.get('usage') or {}
    metadata = {
        'provider': 'opencode-go',
        'model': model,
        'endpoint': endpoint,
        'usage': usage,
    }
    return articles, dialogue, metadata


def render_html(issue_date: str, content_date: str, articles: list[Article], output_path: Path) -> None:
    dt = datetime.strptime(issue_date, '%Y-%m-%d')
    weekdays = '一二三四五六日'
    display_date = f'{dt.year}年{dt.month}月{dt.day}日 星期{weekdays[dt.weekday()]}'
    summary_titles = '；'.join(article.title for article in articles[:5])
    grouped = {section: [] for section in SECTION_ORDER}
    for article in articles:
        grouped.setdefault(article.section, []).append(article)

    parts = [
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>每日AI热点新闻 — {issue_date}</title></head>',
        '<body style="margin:0;padding:0;font-family:PingFang SC,Microsoft YaHei,Arial,sans-serif;background:#eef1f5;">',
        '<table width="100%" cellpadding="0" cellspacing="0" style="padding:24px 0;"><tr><td align="center">',
        '<table width="700" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #c9cdd4;border-radius:10px;overflow:hidden;">',
        '<tr><td style="background:#3b82f6;padding:28px 30px;text-align:center;border-bottom:4px solid #1d4ed8;">',
        '<h1 style="color:#fff;margin:0;font-size:22px;">📰 每日AI热点新闻（试运营）</h1>',
        f'<p style="color:#dbeafe;margin:8px 0 0;font-size:13px;">{display_date}</p></td></tr>',
        '<tr><td style="padding:22px 36px 18px;">',
        f'<p style="color:#374151;font-size:15px;line-height:1.9;margin:0;">今日关注：{html.escape(summary_titles)}。'
        '本期从产品、行业、研究与工具等方向筛选值得跟进的动态。</p></td></tr>',
    ]
    for section in SECTION_ORDER:
        section_articles = grouped.get(section) or []
        if not section_articles:
            continue
        parts.append('<tr><td style="padding:0 36px"><hr style="border:none;border-top:1px solid #e5e7eb;margin:0;"></td></tr>')
        parts.append(f'<tr><td style="padding:22px 36px 26px;"><h2 style="font-size:17px;color:#111827;margin:0 0 16px;padding-bottom:8px;border-bottom:2px solid #dbeafe;">{section}</h2>')
        for article in section_articles:
            escaped_url = html.escape(article.url, quote=True)
            review = f'AI锐评：{html.escape(article.review)}'
            parts.extend([
                '<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">',
                '<tr><td style="padding:14px 18px;background:#f8fafc;">',
                f'<h3 style="font-size:15px;margin:0 0 6px;line-height:1.6;"><a href="{escaped_url}" style="color:#2563eb;text-decoration:none;">{html.escape(article.title)}</a></h3>',
                f'<p data-role="news-body" style="font-size:14px;line-height:2;color:#475569;margin:0 0 8px;">{html.escape(article.summary)}</p>',
                '<table width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:8px 12px;background:#fffbeb;border-left:3px solid #f59e0b;">',
                f'<p style="font-size:13px;color:#6b7280;font-style:italic;margin:0;line-height:1.8;">{review}</p></td></tr></table>',
                f'<p style="font-size:12px;color:#64748b;margin:8px 0 0;">🔗 <a href="{escaped_url}" style="color:#2563eb;text-decoration:none;word-break:break-all;">{escaped_url}</a></p>',
                '</td></tr></table>',
            ])
        parts.append('</td></tr>')
    parts.extend([
        '<tr><td style="padding:20px 36px;text-align:center;background:#f8fafc;">',
        f'<p style="font-size:12px;color:#9ca3af;margin:0;line-height:1.6;">每日AI热点新闻 · {issue_date}<br>内容采集日期：{content_date} · 内容仅供参考</p>',
        '</td></tr></table></td></tr></table></body></html>',
    ])
    output_path.write_text(''.join(parts), encoding='utf-8')


def synthesize_siliconflow(dialogue: list[dict[str, str]], output_path: Path, api_key: str) -> bool:
    segment_dir = Path('/tmp') / f'{output_path.stem}-segments'
    if segment_dir.exists():
        shutil.rmtree(segment_dir)
    segment_dir.mkdir(exist_ok=True)
    segments: list[Path] = []
    for index, turn in enumerate(dialogue):
        speaker = 'alex' if turn['speaker'] == 'S1' else 'anna'
        text = turn['text']
        payload = json.dumps({
            'model': 'FunAudioLLM/CosyVoice2-0.5B',
            'input': text,
            'voice': f'FunAudioLLM/CosyVoice2-0.5B:{speaker}',
            'response_format': 'mp3',
        }).encode()
        request = Request(
            'https://api.siliconflow.cn/v1/audio/speech',
            data=payload,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            method='POST',
        )
        target = segment_dir / f'{index:02d}.mp3'
        try:
            with urlopen(request, timeout=90) as response:
                target.write_bytes(response.read())
            if target.stat().st_size < 1000:
                return False
            segments.append(target)
            time.sleep(0.5)
        except Exception:
            return False
    concat_file = segment_dir / 'concat.txt'
    concat_file.write_text(''.join(f"file '{p.resolve()}'\n" for p in segments), encoding='utf-8')
    subprocess.run(
        ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_file), '-codec:a', 'libmp3lame', '-b:a', '64k', str(output_path)],
        check=True, capture_output=True, text=True,
    )
    success = output_path.exists() and output_path.stat().st_size >= 1_000_000
    shutil.rmtree(segment_dir, ignore_errors=True)
    return success


def fallback_podcast(output_path: Path) -> None:
    subprocess.run(
        ['ffmpeg', '-y', '-stream_loop', '40', '-i', str(VOICE_SAMPLE), '-t', '180', '-codec:a', 'libmp3lame', '-b:a', '64k', str(output_path)],
        check=True, capture_output=True, text=True,
    )


def duration(path: Path) -> float:
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the live daily-news collection and rendering pipeline')
    parser.add_argument('--date', default=date.today().isoformat())
    parser.add_argument('--output-dir', default='dist')
    args = parser.parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')
    output_dir = (REPO_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    content_date, source_url, raw_html = fetch_latest(args.date)
    candidates = parse_articles(raw_html)
    llm_api_key = os.environ.get('OPENCODE_GO_API_KEY', '')
    if not llm_api_key:
        raise RuntimeError('OPENCODE_GO_API_KEY is required; refusing to generate a non-LLM issue')
    articles, dialogue, llm_metadata = call_deepseek(candidates, llm_api_key)
    html_path = output_dir / f'ai-daily-news-html-{args.date}.html'
    podcast_path = output_dir / f'ai-daily-news-podcast-{args.date}.mp3'
    data_path = output_dir / f'news-data-{args.date}.json'
    render_html(args.date, content_date, articles, html_path)
    data_path.write_text(json.dumps([asdict(a) for a in articles], ensure_ascii=False, indent=2), encoding='utf-8')

    tts_mode = 'fallback-sample'
    api_key = os.environ.get('SILICONFLOW_API_KEY', '')
    if api_key and synthesize_siliconflow(dialogue, podcast_path, api_key):
        tts_mode = 'siliconflow-live'
    else:
        fallback_podcast(podcast_path)

    tmp_html = Path('/tmp') / html_path.name
    tmp_podcast = Path('/tmp') / podcast_path.name
    shutil.copy2(html_path, tmp_html)
    shutil.copy2(podcast_path, tmp_podcast)
    shutil.copy2(html_path, SKILL_DIR / 'samples' / f'{args.date}.html')

    report = {
        'mode': 'live-collection',
        'issue_date': args.date,
        'content_date': content_date,
        'source_url': source_url,
        'recipient': 'yyc54321@126.com',
        'article_count': len(articles),
        'candidate_count': len(candidates),
        'llm': llm_metadata,
        'podcast_turns': len(dialogue),
        'tts_mode': tts_mode,
        'html_bytes': html_path.stat().st_size,
        'podcast_bytes': podcast_path.stat().st_size,
        'podcast_duration_seconds': round(duration(podcast_path), 2),
    }
    (output_dir / f'pipeline-report-{args.date}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
