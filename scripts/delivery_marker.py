#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def marker_path(site_dir: Path, date_str: str, phase: str) -> Path:
    return site_dir / 'state' / 'deliveries' / date_str / f'{phase}.json'


def main() -> int:
    parser = argparse.ArgumentParser(description='Check or write idempotent delivery markers')
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check')
    mark = sub.add_parser('mark')
    for item in (check, mark):
        item.add_argument('--site-dir', required=True)
        item.add_argument('--date', required=True)
        item.add_argument('--phase', choices=('morning', 'afternoon'), required=True)
    mark.add_argument('--run-id', required=True)
    mark.add_argument('--recipient', default='yyc54321@126.com')
    args = parser.parse_args()

    path = marker_path(Path(args.site_dir), args.date, args.phase)
    if args.command == 'check':
        print('true' if path.exists() else 'false')
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                'date': args.date,
                'phase': args.phase,
                'recipient': args.recipient,
                'run_id': args.run_id,
                'sent_at': datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
