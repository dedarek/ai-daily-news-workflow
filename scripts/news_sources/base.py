from __future__ import annotations

import html
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 AI-Daily-News-Workflow/2.0"
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "spm",
}


class SourceError(RuntimeError):
    """A source is unavailable, stale, malformed, or below its quality floor."""


@dataclass(frozen=True)
class SourceArticle:
    title: str
    summary: str
    url: str
    section: str = "💼 行业动态"


@dataclass
class SourceResult:
    source_id: str
    source_name: str
    adapter: str
    source_url: str
    status: str
    articles: list[SourceArticle] = field(default_factory=list)
    content_date: str = ""
    generated_at: str = ""
    error: str = ""
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def health_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("articles", None)
        data["candidate_count"] = len(self.articles)
        return data


def clean_text(value: str) -> str:
    value = html.unescape(re.sub(r"(?is)<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def canonical_url(value: str) -> str:
    parsed = urlparse(value.strip())
    kept_query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(kept_query),
            "",
        )
    )


def valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def fetch_bytes(
    url: str,
    *,
    timeout: int = 30,
    max_bytes: int = 2_000_000,
    attempts: int = 3,
) -> tuple[bytes, str]:
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/rss+xml,"
                    "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(max_bytes + 1)
                content_type = response.headers.get("Content-Type", "")
            if len(raw) > max_bytes:
                raise SourceError(f"response exceeds {max_bytes} bytes")
            if not raw:
                raise SourceError("empty response")
            return raw, content_type
        except HTTPError as exc:
            errors.append(f"HTTP {exc.code} {exc.reason}")
            if exc.code < 500 and exc.code != 429:
                break
        except (URLError, TimeoutError, OSError, SourceError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        if attempt < attempts:
            time.sleep(attempt)
    raise SourceError(f"fetch failed for {url}: {' | '.join(errors)}")


def decode_response(raw: bytes, content_type: str = "") -> str:
    charset_match = re.search(r"charset=([\w.-]+)", content_type, flags=re.I)
    candidates = [charset_match.group(1)] if charset_match else []
    candidates.extend(["utf-8", "gb18030"])
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


class TextHTMLParser(HTMLParser):
    """Small reusable parser base that tracks element classes and text."""

    @staticmethod
    def attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attrs}


class SourceAdapter:
    adapter_name = "base"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.source_id = str(config["id"])
        self.source_name = str(config.get("name") or self.source_id)
        self.source_url = str(config["url"])
        self.minimum_items = int(config.get("minimum_items", 1))
        self.maximum_items = int(config.get("maximum_items", 40))

    def collect(self, issue_date: str) -> SourceResult:
        raise NotImplementedError

    def ok(
        self,
        articles: list[SourceArticle],
        started: float,
        *,
        content_date: str = "",
        generated_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SourceResult:
        if len(articles) < self.minimum_items:
            raise SourceError(
                f"parsed {len(articles)} candidates; minimum is {self.minimum_items}"
            )
        return SourceResult(
            source_id=self.source_id,
            source_name=self.source_name,
            adapter=self.adapter_name,
            source_url=self.source_url,
            status="ok",
            articles=articles[: self.maximum_items],
            content_date=content_date,
            generated_at=generated_at,
            duration_ms=round((time.monotonic() - started) * 1000),
            metadata=metadata or {},
        )

    def failed(self, exc: Exception, started: float) -> SourceResult:
        return SourceResult(
            source_id=self.source_id,
            source_name=self.source_name,
            adapter=self.adapter_name,
            source_url=self.source_url,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=round((time.monotonic() - started) * 1000),
        )


def parse_iso_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")
