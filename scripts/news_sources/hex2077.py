from __future__ import annotations

import re
import time
from html.parser import HTMLParser
from urllib.parse import urlparse

from .base import (
    SourceAdapter,
    SourceArticle,
    SourceError,
    clean_text,
    decode_response,
    fetch_bytes,
)


FORBIDDEN_URL_PARTS = (
    "hex2077.dev",
    "aibase.com",
    "hubtoday",
    "wappoc_appmsgcaptcha",
)


def valid_original_url(url: str) -> bool:
    lower = url.lower()
    if any(part in lower for part in FORBIDDEN_URL_PARTS):
        return False
    parsed = urlparse(url)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.path not in {"", "/"}
    )


def section_for(source_heading: str, index: int) -> str:
    lowered = source_heading.lower()
    if index == 0:
        return "🔥 今日焦点"
    if "开源" in source_heading:
        return "🔓 开源热榜"
    if "研究" in source_heading:
        return "💡 前沿研究"
    if any(word in lowered for word in ("agent", "工具", "社媒")):
        return "🤖 Agent & 工具"
    if any(word in source_heading for word in ("产品", "功能", "发布")):
        return "🚀 产品发布"
    return "💼 行业动态"


def expand_summary(title: str, raw: str) -> str:
    raw = clean_text(raw)
    if raw.startswith(title):
        raw = raw[len(title) :].lstrip("。 ")
    sentences = [item.strip() for item in re.split(r"(?<=[。！？])", raw) if item.strip()]
    summary = "".join(sentences[:5]).strip() or raw
    if summary and not summary.endswith(("。", "！", "？")):
        summary += "。"
    return summary[:420]


class HexDailyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.heading_depth = 0
        self.heading_text: list[str] = []
        self.current_heading = ""
        self.in_item = False
        self.item_depth = 0
        self.item_text: list[str] = []
        self.item_links: list[str] = []
        self.strong_depth = 0
        self.title_text: list[str] = []
        self.title_complete = False
        self.items: list[tuple[str, str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"h2", "h3"}:
            self.heading_depth += 1
            self.heading_text = []
        if tag == "li" and not self.in_item:
            self.in_item = True
            self.item_depth = 1
            self.item_text = []
            self.item_links = []
            self.title_text = []
            self.title_complete = False
        elif self.in_item:
            if tag == "li":
                self.item_depth += 1
            if tag == "strong":
                self.strong_depth += 1
            if tag == "a":
                href = values.get("href") or ""
                if href.startswith(("http://", "https://")):
                    self.item_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h2", "h3"} and self.heading_depth:
            self.current_heading = clean_text("".join(self.heading_text))
            self.heading_depth -= 1
        if not self.in_item:
            return
        if tag == "strong" and self.strong_depth:
            self.strong_depth -= 1
            if self.title_text:
                self.title_complete = True
        if tag == "li":
            self.item_depth -= 1
            if self.item_depth == 0:
                title = clean_text("".join(self.title_text)).rstrip("。")
                body = clean_text("".join(self.item_text))
                url = next(
                    (item for item in self.item_links if valid_original_url(item)),
                    "",
                )
                if title and body and url:
                    self.items.append((self.current_heading, title, body, url))
                self.in_item = False

    def handle_data(self, data: str) -> None:
        if self.heading_depth:
            self.heading_text.append(data)
        if self.in_item:
            self.item_text.append(data)
            if self.strong_depth and not self.title_complete:
                self.title_text.append(data)


def parse_hex_daily_html(raw_html: str, maximum_items: int = 20) -> list[SourceArticle]:
    parser = HexDailyParser()
    parser.feed(raw_html)
    articles: list[SourceArticle] = []
    seen: set[tuple[str, str]] = set()
    for heading, title, body, url in parser.items:
        if any(word in heading for word in ("多渠道", "摘要")):
            continue
        key = (title.casefold(), url)
        if key in seen:
            continue
        seen.add(key)
        articles.append(
            SourceArticle(
                title=title,
                summary=expand_summary(title, body),
                url=url,
                section=section_for(heading, len(articles)),
            )
        )
        if len(articles) >= maximum_items:
            break
    return articles


class Hex2077Adapter(SourceAdapter):
    adapter_name = "hex2077"

    def collect(self, issue_date: str):
        started = time.monotonic()
        try:
            url = self.source_url.format(
                date=issue_date,
                year_month=issue_date[:7],
            )
            raw, content_type = fetch_bytes(url)
            if len(raw) < int(self.config.get("minimum_bytes", 10_000)):
                raise SourceError(f"source page too small: {len(raw)} bytes")
            articles = parse_hex_daily_html(
                decode_response(raw, content_type),
                self.maximum_items,
            )
            result = self.ok(
                articles,
                started,
                content_date=issue_date,
                metadata={"resolved_url": url, "time_rule": "content date equals issue date"},
            )
            result.source_url = url
            return result
        except Exception as exc:
            return self.failed(exc, started)
