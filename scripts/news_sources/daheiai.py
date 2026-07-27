from __future__ import annotations

import email.utils
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

from .base import (
    SourceAdapter,
    SourceArticle,
    SourceError,
    canonical_url,
    clean_text,
    decode_response,
    fetch_bytes,
    valid_http_url,
)


CHINA_TZ = timezone(timedelta(hours=8))


class DescriptionLinkParser(HTMLParser):
    def __init__(self, source_host: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_host = source_host
        self.capture = False
        self.href = ""
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        if valid_http_url(href) and urlparse(href).netloc.lower() != self.source_host:
            self.capture = True
            self.href = href
            self.text = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.capture:
            title = clean_text("".join(self.text))
            if len(title) >= 8:
                self.links.append((title, self.href))
            self.capture = False
            self.href = ""
            self.text = []


def child_text(item: ET.Element, names: set[str]) -> str:
    for child in item.iter():
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name in names and child.text:
            return child.text.strip()
    return ""


def parse_rss_datetime(value: str) -> datetime:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError) as exc:
        raise SourceError(f"invalid RSS publication time {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(CHINA_TZ)


def parse_daheiai_rss(
    raw_xml: str,
    issue_date: str,
    *,
    maximum_items: int = 25,
) -> tuple[list[SourceArticle], datetime | None, int]:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise SourceError(f"invalid RSS XML: {exc}") from exc
    issue_day = datetime.strptime(issue_date, "%Y-%m-%d").date()
    source_host = "news.daheiai.com"
    articles: list[SourceArticle] = []
    newest: datetime | None = None
    selected_entries = 0
    seen: set[str] = set()

    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1].lower() not in {"item", "entry"}:
            continue
        title = clean_text(child_text(item, {"title"}))
        link = child_text(item, {"link"})
        if not link:
            for child in item:
                if child.tag.rsplit("}", 1)[-1].lower() == "link":
                    link = child.attrib.get("href", "")
                    if link:
                        break
        description_raw = child_text(item, {"description", "summary", "content", "encoded"})
        published_raw = child_text(item, {"pubdate", "published", "updated", "date"})
        if not published_raw:
            continue
        published_at = parse_rss_datetime(published_raw)
        if published_at.date() not in {issue_day, issue_day - timedelta(days=1)}:
            continue
        selected_entries += 1
        if newest is None or published_at > newest:
            newest = published_at

        link_parser = DescriptionLinkParser(source_host)
        link_parser.feed(description_raw)
        for linked_title, linked_url in link_parser.links:
            canonical = canonical_url(linked_url)
            if canonical in seen:
                continue
            seen.add(canonical)
            articles.append(
                SourceArticle(
                    title=linked_title,
                    summary=clean_text(description_raw)[:500],
                    url=linked_url,
                )
            )
            if len(articles) >= maximum_items:
                return articles, newest, selected_entries

        if len(articles) >= maximum_items:
            break
        if title and valid_http_url(link):
            canonical = canonical_url(link)
            if canonical not in seen:
                seen.add(canonical)
                summary = clean_text(description_raw)
                articles.append(
                    SourceArticle(
                        title=title,
                        summary=(summary or f"{title}。")[:500],
                        url=link,
                    )
                )
    return articles, newest, selected_entries


class DaheiAIAdapter(SourceAdapter):
    adapter_name = "daheiai_rss"

    def collect(self, issue_date: str):
        started = time.monotonic()
        try:
            raw, content_type = fetch_bytes(
                self.source_url,
                max_bytes=int(self.config.get("maximum_bytes", 4_000_000)),
            )
            articles, newest, selected_entries = parse_daheiai_rss(
                decode_response(raw, content_type),
                issue_date,
                maximum_items=self.maximum_items,
            )
            if newest is None:
                raise SourceError(f"RSS has no entries for {issue_date} or the preceding day")
            if newest.date().isoformat() != issue_date:
                raise SourceError(
                    f"stale RSS: newest item is {newest.isoformat()}, expected an item on {issue_date}"
                )
            return self.ok(
                articles,
                started,
                content_date=issue_date,
                generated_at=newest.isoformat(),
                metadata={
                    "time_rule": "newest RSS item must be published on issue date (Asia/Shanghai)",
                    "selected_feed_entries": selected_entries,
                },
            )
        except Exception as exc:
            return self.failed(exc, started)
