# Migration Note: `perception.screen` optional field expansion

`perception.screen` has been expanded with additional **optional** context fields
(`window_class`, `process_name`, `browser_domain`, `browser_url_full`,
`ui_context`, `raw_artifact_retained`, `redaction_notes`).

## Compatibility

- Older payloads remain valid.
- No existing required fields were renamed or removed.
- New fields are optional and additive.

## Privacy behavior

- `browser_url_full` is emitted only when `privacy_class=private` and adapter
  flag `--include-url-full` is explicitly set.
- `text_excerpt` remains opt-in and is truncated.
