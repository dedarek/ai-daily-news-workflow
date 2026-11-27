# Private delivery recovery

Keep `AI_DAILY_PRIVATE_DELIVERY_READY` unset while migrating. Public GitHub Pages has the HTML/media and sanitized manifests, never state or the recipient roster.

1. Provision an initialized **private** repository with default branch `main`. Give its workflow token access to **only that private repository**, with Contents read/write.
2. In the private repository copy the prior roster as `recipients.json` and the prior `state/delivery-progress/` and `state/deliveries/` trees at their original paths. Check that the prior completed or partial runs and both audiences survive. Commit an empty `migration-complete` marker after this check. Do not paste the roster or state into logs, issues, or public commits.
3. In the public workflow repository set variable `AI_DAILY_PRIVATE_STATE_REPO` to the private repository slug and secret `AI_DAILY_PRIVATE_STATE_TOKEN` to the scoped token. Supply the model and media endpoints as secret values using the existing variable names `LENOVO_LLM_BASE_URL` and `AI_DAILY_VIDEO_API_BASE_URL` rather than embedding them in workflow files. The workflow verifies visibility before it checks out the destination. Keep repository user access at least as narrow as the intended administrators.
4. Once private state and settings have been verified, set repository variable `AI_DAILY_PRIVATE_DELIVERY_READY=true`. Do not rerun historical actions. The first control run should use no send, then inspect only the public output, guard and private storage checks before allowing the normal send. Leaving the variable unset keeps workflows paused.
5. A stored `in_flight` record means a connection interruption made acceptance uncertain. Resolve against mail-provider submission evidence before marking it sent or retryable in private storage. Do not clear all state to retry. Explicit SMTP refusals are retryable without repeating accepted addresses.

Git commit history, old Actions logs/artifacts, caches, and any copies are outside this forward migration. Retire them as a separately coordinated operation; ordinary redaction commits do not remove that history.
