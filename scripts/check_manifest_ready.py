#!/usr/bin/env python3
"""Exit 0 if the morning issue manifest is published and ready, else non-zero.

Extracted from an inline heredoc in the afternoon workflow: an inline
`python3 - <<'PY'` block cannot be indented to the YAML block-scalar base
indent without breaking either the YAML parser or Python indentation, so the
check lives in a real file instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def is_ready(manifest_path: Path) -> tuple[bool, str]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f'manifest unreadable: {exc}'
    if manifest.get('status') != 'ready':
        return False, f"manifest status is {manifest.get('status')!r}, expected 'ready'"
    published = manifest.get('published_artifacts')
    if not isinstance(published, dict) or not published.get('html') or not published.get('audio'):
        return False, 'manifest missing published html/audio artifacts'
    return True, 'ready'


def main() -> int:
    if len(sys.argv) != 2:
        print('usage: check_manifest_ready.py <manifest.json>', file=sys.stderr)
        return 2
    ready, reason = is_ready(Path(sys.argv[1]))
    if not ready:
        print(reason, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
