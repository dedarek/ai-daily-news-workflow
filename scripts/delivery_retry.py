"""Persist SMTP outcomes at recipient granularity; quarantine ambiguous outcomes."""
import smtplib
from datetime import datetime, timezone


def run_delivery(batches, status, send, checkpoint, retries, sleep, retry_delay, between):
    sent, failed = status['sent'], status['failed']
    inflight = status.setdefault('in_flight', {})
    if not isinstance(inflight, dict):
        raise ValueError('Invalid in-flight state')
    for index, batch in enumerate(batches, 1):
        remaining = [addr for addr in batch if addr.lower() not in sent and addr.lower() not in inflight]
        for attempt in range(retries):
            if not remaining:
                break
            now = datetime.now(timezone.utc).isoformat()
            for addr in remaining:
                inflight[addr.lower()] = {'recipient': addr, 'queued_at': now}
            checkpoint(status)
            try:
                refused = send(remaining)
            except smtplib.SMTPRecipientsRefused as exc:
                refused = exc.recipients
            except smtplib.SMTPAuthenticationError:
                refused = dict.fromkeys(remaining, (535, None))
            except (smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
                refused = dict.fromkeys(remaining, (exc.smtp_code, None))
            except (smtplib.SMTPException, OSError):
                # After a connection disappears, the server might already have accepted DATA.
                # Leave the pre-send record in place; a rerun cannot resend these blind.
                return
            refusal_codes = {a.lower(): info[0] for a, info in refused.items()}
            temporary = []
            for addr in remaining:
                key = addr.lower()
                code = refusal_codes.get(key)
                if code is None:
                    sent[key] = {'recipient': addr, 'sent_at': now}
                    failed.pop(key, None)
                else:
                    failed[key] = {'recipient': addr, 'failed_at': now, 'smtp_code': code}
                    if 400 <= code < 500:
                        temporary.append(addr)
                inflight.pop(key, None)
            checkpoint(status)
            remaining = temporary
            if remaining and attempt + 1 < retries:
                sleep(retry_delay)
        if index < len(batches):
            between(index)
