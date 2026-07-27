from __future__ import annotations

import re
import time
from datetime import datetime
from html.parser import HTMLParser

from .base import (
    SourceAdapter,
    SourceArticle,
    SourceError,
    clean_text,
    decode_response,
    fetch_bytes,
    valid_http_url,
)


class SatoriPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_card = False
        self.card_depth = 0
        self.capture = ""
        self.capture_depth = 0
        self.buffer: list[str] = []
        self.current: dict[str, str] = {}
        self.cards: list[dict[str, str]] = []
        self.page_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "article" and "card" in classes and not self.in_card:
            self.in_card = True
            self.card_depth = 1
            self.current = {}
            return
        if not self.in_card:
            return
        if tag == "article":
            self.card_depth += 1
        if tag == "a" and not self.current.get("url"):
            href = values.get("href") or ""
            if valid_http_url(href):
                self.current["url"] = href
                self.capture = "title"
                self.capture_depth = 1
                self.buffer = []
        elif tag == "p" and "sum" in classes:
            self.capture = "summary"
            self.capture_depth = 1
            self.buffer = []
        elif tag == "div" and "src" in classes:
            self.capture = "source"
            self.capture_depth = 1
            self.buffer = []
        elif self.capture:
            self.capture_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.capture:
            self.capture_depth -= 1
            if self.capture_depth == 0:
                self.current[self.capture] = clean_text("".join(self.buffer))
                self.capture = ""
                self.buffer = []
        if self.in_card and tag == "article":
            self.card_depth -= 1
            if self.card_depth == 0:
                if self.current.get("title") and self.current.get("url"):
                    self.cards.append(self.current)
                self.current = {}
                self.in_card = False

    def handle_data(self, data: str) -> None:
        self.page_text.append(data)
        if self.capture:
            self.buffer.append(data)


def parse_satori_html(
    raw_html: str,
) -> tuple[str, str, list[SourceArticle]]:
    parser = SatoriPageParser()
    parser.feed(raw_html)
    page_text = clean_text(" ".join(parser.page_text))
    title_match = re.search(r"每日\s*AI\s*速览\s*[·・]?\s*(20\d{2}-\d{2}-\d{2})", page_text)
    if not title_match:
        title_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", page_text)
    generated_match = re.search(
        r"生成于\s*(20\d{2}-\d{2}-\d{2})\s+(\d{2}:\d{2})",
        page_text,
    )
    if not title_match:
        raise SourceError("cannot find Satori content date")
    if not generated_match:
        raise SourceError("cannot find Satori generation time")

    articles: list[SourceArticle] = []
    for card in parser.cards:
        title = clean_text(card.get("title", ""))
        summary = clean_text(card.get("summary", ""))
        url = card.get("url", "").strip()
        if not title or not summary or not valid_http_url(url):
            continue
        articles.append(
            SourceArticle(
                title=title,
                summary=summary[:500],
                url=url,
                section="💡 前沿研究" if "arxiv.org" in url else "💼 行业动态",
            )
        )
    generated_at = f"{generated_match.group(1)}T{generated_match.group(2)}:00+08:00"
    return title_match.group(1), generated_at, articles


class SatoriAdapter(SourceAdapter):
    adapter_name = "satori"

    def collect(self, issue_date: str):
        started = time.monotonic()
        try:
            raw, content_type = fetch_bytes(self.source_url)
            content_date, generated_at, articles = parse_satori_html(
                decode_response(raw, content_type)
            )
            generated_date = datetime.fromisoformat(generated_at).date().isoformat()
            # Satori publishes at 04:00 and summarizes the previous calendar day.
            # Product semantics treat that generated edition as today's source.
            if generated_date != issue_date:
                raise SourceError(
                    f"stale edition: generated date {generated_date}, expected {issue_date}; "
                    f"content date is {content_date}"
                )
            return self.ok(
                articles,
                started,
                content_date=content_date,
                generated_at=generated_at,
                metadata={
                    "time_rule": "generation date equals issue date; edition is treated as today's digest",
                    "edition_semantics": "today",
                },
            )
        except Exception as exc:
            return self.failed(exc, started)
