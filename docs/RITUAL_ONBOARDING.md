# Ritual Onboarding Checklist

Welcome to the cathedral! Follow this one‑page ritual when submitting your first pull request.

1. Read the [Tag Extension Guide](TAG_EXTENSION_GUIDE.md), [Privilege Policy](../CONTRIBUTING.md), and [Code of Conduct](../CODE_OF_CONDUCT.md).
2. Bless your pull request by mentioning a reviewer and linking the discussion issue.
3. After review, complete the reviewer sign‑off in the PR description.
4. Join the community welcome channel and introduce yourself.
5. Call `require_admin_banner()` and **immediately** `require_lumos_approval()` for each new script, commit, or federation event.
6. Be aware that Lumos now runs a reflex daemon that may auto-bless unattended actions and annotate them for later review.

## Why memory matters
Audit logs preserve community memory. Past audits recovered missing context that helped resolve disputes and comforted contributors who felt unheard. Treat each log entry as a fragment of shared history.
