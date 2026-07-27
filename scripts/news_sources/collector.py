from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .base import SourceAdapter, SourceArticle, SourceResult, canonical_url
from .daheiai import DaheiAIAdapter
from .hex2077 import Hex2077Adapter
from .satori import SatoriAdapter


ADAPTERS: dict[str, type[SourceAdapter]] = {
    Hex2077Adapter.adapter_name: Hex2077Adapter,
    SatoriAdapter.adapter_name: SatoriAdapter,
    DaheiAIAdapter.adapter_name: DaheiAIAdapter,
}


def normalized_title(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def duplicate_title(candidate: str, accepted: list[str]) -> bool:
    normalized = normalized_title(candidate)
    if not normalized:
        return True
    for existing in accepted:
        if normalized == existing:
            return True
        if min(len(normalized), len(existing)) >= 12:
            if SequenceMatcher(None, normalized, existing).ratio() >= 0.9:
                return True
    return False


def merge_round_robin(
    results: list[SourceResult],
    maximum_candidates: int,
) -> list[SourceArticle]:
    queues = [list(result.articles) for result in results if result.status == "ok"]
    merged: list[SourceArticle] = []
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    while queues and len(merged) < maximum_candidates:
        next_queues: list[list[SourceArticle]] = []
        for queue in queues:
            if not queue:
                continue
            candidate = queue.pop(0)
            canonical = canonical_url(candidate.url)
            if canonical not in seen_urls and not duplicate_title(candidate.title, seen_titles):
                merged.append(candidate)
                seen_urls.add(canonical)
                seen_titles.append(normalized_title(candidate.title))
            if queue:
                next_queues.append(queue)
            if len(merged) >= maximum_candidates:
                break
        queues = next_queues
    return merged


def load_source_config(path: Path) -> dict[str, Any]:
    configured = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configured, dict):
        raise RuntimeError(f"Source config must be an object: {path}")
    sources = configured.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RuntimeError(f"Source config must contain a non-empty sources list: {path}")
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise RuntimeError(f"Each source config must be an object: {source!r}")
        source_id = str(source.get("id") or "")
        adapter = str(source.get("adapter") or "")
        if not source_id or source_id in seen:
            raise RuntimeError(f"Source id is missing or duplicated: {source_id!r}")
        if adapter not in ADAPTERS:
            raise RuntimeError(f"Unknown adapter {adapter!r} for source {source_id!r}")
        if not source.get("url"):
            raise RuntimeError(f"Source {source_id!r} is missing url")
        seen.add(source_id)
    return configured


def _run_adapter(adapter: SourceAdapter, issue_date: str) -> SourceResult:
    return adapter.collect(issue_date)


def collect_news_sources(
    issue_date: str,
    config_path: Path,
) -> tuple[list[SourceArticle], dict[str, Any]]:
    started = time.monotonic()
    config = load_source_config(config_path)
    enabled = [item for item in config["sources"] if item.get("enabled", True)]
    if not enabled:
        raise RuntimeError("No news source is enabled")
    adapters = [ADAPTERS[item["adapter"]](item) for item in enabled]
    result_by_id: dict[str, SourceResult] = {}
    with ThreadPoolExecutor(max_workers=min(len(adapters), 6)) as executor:
        future_map = {
            executor.submit(_run_adapter, adapter, issue_date): adapter
            for adapter in adapters
        }
        for future in as_completed(future_map):
            adapter = future_map[future]
            try:
                result = future.result()
            except Exception as exc:  # Defensive boundary between independent adapters.
                result = adapter.failed(exc, started)
            result_by_id[result.source_id] = result

    # Preserve configuration order so merge behavior and reports stay deterministic.
    results = [result_by_id[item["id"]] for item in enabled]
    maximum_candidates = int(config.get("maximum_candidates", 60))
    candidates = merge_round_robin(results, maximum_candidates)
    successful = [item for item in results if item.status == "ok"]
    failed = [item for item in results if item.status != "ok"]
    minimum_usable = int(config.get("minimum_usable_candidates", 12))
    if not successful:
        overall_status = "failed"
    elif failed:
        overall_status = "degraded"
    else:
        overall_status = "ok"
    health = {
        "schema_version": 1,
        "issue_date": issue_date,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "pipeline_can_continue": bool(successful) and len(candidates) >= minimum_usable,
        "minimum_usable_candidates": minimum_usable,
        "candidate_count_before_dedup": sum(len(item.articles) for item in successful),
        "candidate_count_after_dedup": len(candidates),
        "successful_source_count": len(successful),
        "failed_source_count": len(failed),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "sources": [item.health_dict() for item in results],
    }
    return candidates, health
