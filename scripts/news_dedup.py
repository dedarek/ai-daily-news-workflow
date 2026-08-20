from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from news_sources.base import canonical_url


HIGH_CONFIDENCE_ACTIONS = {
    "acquisition": ("收购", "并购", "买下", "acquire", "acquisition", "buys", "bought"),
    "funding": ("融资", "募资", "funding", "fundraise", "raises"),
    "lawsuit": ("起诉", "诉讼", "lawsuit", "sues", "sued"),
    "partnership": ("合作", "结盟", "partnership", "partners with", "teams up"),
    "layoff": ("裁员", "layoff", "lays off", "job cuts"),
}
ENTITY_STOPWORDS = {
    "agent", "agents", "ai", "api", "app", "apps", "artificial", "blog",
    "company", "deep", "intelligence", "llm", "model", "models", "news",
    "open", "platform", "report", "the", "tool", "tools", "with",
}


def delivered_dates(site_dir: Path) -> set[str]:
    """Return dates that have at least one successful email delivery marker."""
    root = site_dir / "state" / "deliveries"
    if not root.exists():
        return set()
    delivered: set[str] = set()
    for day_dir in root.iterdir():
        if not day_dir.is_dir():
            continue
        if (day_dir / "morning.json").exists() or (day_dir / "afternoon.json").exists():
            delivered.add(day_dir.name)
    return delivered


def filter_state_to_delivered(state: dict[str, Any], site_dir: Path) -> dict[str, Any]:
    """Discard generated-but-never-sent issues from cross-day dedupe memory."""
    sent_days = delivered_dates(site_dir)
    raw_days = state.get("days") if isinstance(state, dict) else {}
    days = raw_days if isinstance(raw_days, dict) else {}
    return {
        "window_days": int(state.get("window_days") or 7),
        "days": {
            day: payload
            for day, payload in days.items()
            if day in sent_days and isinstance(payload, dict)
        },
    }


def recent_sent_articles(
    state_path: Path,
    issue_date: str,
    *,
    window_days: int = 7,
) -> dict[str, list[dict[str, str]]]:
    """Load only sent/selected articles from the seven calendar days before an issue."""
    if not state_path.exists():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    days = state.get("days") if isinstance(state, dict) else {}
    if not isinstance(days, dict):
        return {}

    issue_day = datetime.strptime(issue_date, "%Y-%m-%d").date()
    cutoff = issue_day - timedelta(days=window_days)
    recent: dict[str, list[dict[str, str]]] = {}
    for day, payload in sorted(days.items(), reverse=True):
        try:
            parsed_day = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            continue
        if parsed_day >= issue_day or parsed_day < cutoff or not isinstance(payload, dict):
            continue
        selected = [
            {
                "date": str(item.get("date") or day),
                "title": str(item.get("title", "")).strip(),
                "summary": str(item.get("summary", "")).strip()[:500],
                "url": str(item.get("url", "")).strip(),
            }
            for item in payload.get("selected", [])
            if isinstance(item, dict)
            and str(item.get("title", "")).strip()
            and str(item.get("url", "")).strip()
        ]
        if selected:
            recent[day] = selected
    return recent


def flatten_recent_sent(
    recent: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    return [item for day in recent.values() for item in day]


def exact_recent_url_matches(
    candidate_urls: list[str],
    recent: dict[str, list[dict[str, str]]],
) -> dict[str, dict[str, str]]:
    recent_by_url = {
        canonical_url(item["url"]): item
        for item in flatten_recent_sent(recent)
        if item.get("url")
    }
    matches: dict[str, dict[str, str]] = {}
    for url in candidate_urls:
        previous = recent_by_url.get(canonical_url(url))
        if previous:
            matches[url] = previous
    return matches


def _action_groups(text: str) -> set[str]:
    lowered = text.casefold()

    def contains(alias: str) -> bool:
        if alias.isascii():
            return bool(
                re.search(
                    rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
                    lowered,
                )
            )
        return alias in lowered

    return {
        group
        for group, aliases in HIGH_CONFIDENCE_ACTIONS.items()
        if any(contains(alias) for alias in aliases)
    }


def _entity_tokens(text: str) -> set[str]:
    tokens = {
        token.casefold().strip("-._")
        for token in re.findall(r"[A-Za-z][A-Za-z0-9._-]{2,}", text)
    }
    return {
        token
        for token in tokens
        if token and token not in ENTITY_STOPWORDS and not token.isdigit()
    }


def high_confidence_event_matches(
    candidates: list[dict[str, str]],
    recent: dict[str, list[dict[str, str]]],
) -> dict[str, dict[str, Any]]:
    """Catch obvious same-event rewrites before the semantic LLM review.

    This deliberately covers only event types with a concrete action and at least
    two shared named ASCII entities. Broader release/update similarity is left to
    the focused semantic reviewer to avoid suppressing genuinely new versions.
    """
    matches: dict[str, dict[str, Any]] = {}
    previous_items = flatten_recent_sent(recent)
    for candidate in candidates:
        current_url = candidate.get("url", "")
        current_text = f'{candidate.get("title", "")} {candidate.get("summary", "")}'
        current_actions = _action_groups(current_text)
        current_entities = _entity_tokens(current_text)
        if not current_actions or len(current_entities) < 2:
            continue
        for previous in previous_items:
            previous_text = f'{previous.get("title", "")} {previous.get("summary", "")}'
            shared_actions = current_actions & _action_groups(previous_text)
            shared_entities = current_entities & _entity_tokens(previous_text)
            if shared_actions and len(shared_entities) >= 2:
                matches[current_url] = {
                    "previous": previous,
                    "actions": sorted(shared_actions),
                    "entities": sorted(shared_entities),
                }
                break
    return matches
