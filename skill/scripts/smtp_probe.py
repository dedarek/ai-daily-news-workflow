#!/usr/bin/env python3
import argparse
import json
import smtplib
import ssl
import sys
import time
from pathlib import Path

def probe_ssl(host, port, timeout):
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as client:
            code, message = client.noop()
            cipher = client.sock.cipher() if client.sock else None
        return {
            'success': 200 <= code < 400,
            'smtp_code': code,
            'output': message.decode(errors='replace') if isinstance(message, bytes) else str(message),
            'cipher': cipher,
        }
    except Exception as exc:
        return {'success': False, 'error': f'{type(exc).__name__}: {exc}'}


def probe_starttls(host, port, timeout):
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=timeout) as client:
            client.ehlo()
            client.starttls(context=context)
            code, message = client.noop()
            cipher = client.sock.cipher() if client.sock else None
        return {
            'success': 200 <= code < 400,
            'smtp_code': code,
            'output': message.decode(errors='replace') if isinstance(message, bytes) else str(message),
            'cipher': cipher,
        }
    except Exception as exc:
        return {'success': False, 'error': f'{type(exc).__name__}: {exc}'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='smtp.163.com')
    ap.add_argument('--ssl-port', type=int, default=465)
    ap.add_argument('--starttls-port', type=int, default=587)
    ap.add_argument('--retries', type=int, default=2)
    ap.add_argument('--sleep-seconds', type=float, default=2.0)
    ap.add_argument('--timeout-seconds', type=float, default=12.0)
    ap.add_argument('--json-out')
    args = ap.parse_args()

    attempts = []
    ok = False
    mode = None
    for i in range(args.retries):
        rec = probe_ssl(args.host, args.ssl_port, args.timeout_seconds)
        rec['mode'] = 'ssl'
        rec['attempt'] = i + 1
        attempts.append(rec)
        if rec['success']:
            ok = True
            mode = 'ssl'
            break
        if i < args.retries - 1:
            time.sleep(args.sleep_seconds)

    if not ok:
        rec = probe_starttls(args.host, args.starttls_port, args.timeout_seconds)
        rec['mode'] = 'starttls'
        rec['attempt'] = 1
        attempts.append(rec)
        if rec['success']:
            ok = True
            mode = 'starttls'

    result = {
        'host': args.host,
        'ssl_port': args.ssl_port,
        'starttls_port': args.starttls_port,
        'ok': ok,
        'mode': mode,
        'attempts': attempts,
    }

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
