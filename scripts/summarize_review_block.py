#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print('Afternoon review blocked delivery.')
        return 0
    path = Path(sys.argv[1])
    try:
        report = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        print('Afternoon review blocked delivery.')
        return 0

    reasons = report.get('blocking_reasons') or []
    review = report.get('llm_review') or {}
    issues = review.get('issues') or []
    parts: list[str] = []
    if reasons:
        parts.append('Blocking reasons: ' + '; '.join(map(str, reasons)))
    if issues:
        parts.append('Review issues: ' + '; '.join(map(str, issues[:3])))
    print(' | '.join(parts) or 'Afternoon review blocked delivery.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
