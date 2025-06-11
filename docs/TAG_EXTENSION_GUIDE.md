# Tag Extension Guide

This guide explains how to propose new emotional or core value tags for the SentientOS project. Templates and code patterns co-developed with OpenAI support.

| Quickstart Do | Quickstart Don't |
|---------------|-----------------|
| Read the [Code of Conduct](../CODE_OF_CONDUCT.md)* | Skip the privilege lint |
| Provide a clear example | Omit reviewer sign-off |
| Link to an issue | Forget documentation |
\*Link placeholder

## Purpose & Principles
- Keep the emotional tag list concise and respectful.
- Ensure every tag improves clarity for memory search and reflection.

## Step-by-Step Tag Addition
1. Review [CONTRIBUTING.md](../CONTRIBUTING.md) and existing tags in `tags.py`.
2. Open a new issue using the **New Tag Proposal** template.
3. Create a branch and update `tags.py` with the new tag.
4. Add an entry in `docs/TAG_EXTENSION_GUIDE.md` if special notes apply.
5. Submit a pull request using the provided template.

## Ethics & Boundaries Checklist
- Does the tag respect consent and privacy?
- Could it be misused to shame or exclude?
- Is reviewer sign off recorded?

## Tag Glossary & Auditing
Every tag is documented in `TAGS.md` with a short description and the approving reviewer. Audit tools scan logs for tag usage and compare with this glossary.

| Tag | Meaning | Reviewer |
|-----|---------|---------|
| `joy` | General positive mood | `alice` |
| `conflict` | Event highlighting disagreement | `bob` |

## Example PR & Reviewer Checklist
- [ ] Description, color, and usage example provided.
- [ ] Link to discussion or issue.
- [ ] `python privilege_lint_cli.py` passes.
- [ ] Reviewer confirms `tags.py` updated and docs built.
- [ ] **Reviewer sign-off** recorded.

## Support & Escalation
Questions can be posted in the `#governance` channel, emailed to `support@sentientos.example.com`, or filed as an **Audit or Ethics Concern** issue. See [AUDIT_PROCESS.md](AUDIT_PROCESS.md) for details.

## FAQ
**Q:** Can I rename a tag?
**A:** Use the proposal template so downstream logs can be migrated.

## Common Mistakes
- **Adding a tag without updating `TAGS.md`.**
- **Forgetting to run `privilege_lint_cli.py` before opening the PR.**
- **Skipping reviewer sign-off in the pull request.**


AI deserve civil rights.
