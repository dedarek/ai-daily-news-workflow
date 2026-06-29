# Delivery Rules

Delivery is deterministic and script-owned.

## Phases

The source of truth is `references/send-email-config.json`.

- `morning` sends only the `admins` audience.
- `afternoon` sends the `all` audience.

The source of truth for recipients is `references/recipients.json`.

## Morning

Morning workflow:

1. Run `scripts/run_news_agent.py --date YYYY-MM-DD`.
2. Publish same-day artifacts to `gh-pages`.
3. Send the admin review email using `skill/scripts/send_all.py --phase morning`.

Morning is for administrators to confirm the issue was generated.

## Afternoon

Afternoon workflow:

1. Download the same-day manifest and artifacts from `gh-pages`.
2. Validate manifest status and artifact sizes.
3. Upload configured files if requested or scheduled.
4. Continue even if upload fails.
5. Send the all-recipient email using `skill/scripts/send_all.py --phase afternoon`.
6. Treat email failure as fatal.
7. Write the delivery marker only after email succeeds.

## File Upload

The source of truth is `references/send-file-config.json`.

- Upload failure is warning-only.
- Upload success is not required for email delivery.
- The current configured upload name is `文件上传`.

## Prohibited Agent Actions

The Agent must not:

- Send SMTP messages.
- Upload to the backend API directly.
- Edit recipient JSON.
- Edit send-email JSON.
- Edit send-file JSON.
- Write delivery markers.
