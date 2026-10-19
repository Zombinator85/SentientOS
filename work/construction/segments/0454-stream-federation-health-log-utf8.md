# Sequence 454 — Stream Federation Health logs and isolate invalid UTF-8 rows

**Construction status: source and regression coverage are prepared for exact-head hosted verification.** Sequence 452 made the JSONL parser skip malformed JSON and invalid record shapes, but the whole log was still decoded at once. A single invalid UTF-8 byte anywhere in the file could abort the health report before valid records were evaluated.

The parser now reads the log incrementally as bytes, decodes each record independently, and skips only rows that cannot be decoded as UTF-8 before applying the existing JSON, mapping, peer-key, timestamp, and time-window checks. The regression places an invalid-UTF-8 record between two valid records and verifies both valid peer/event records remain represented. Report fields, authority gates, input ordering, and configured-snapshot scope are unchanged.

This is a local input-integrity improvement. It makes no claim about live federation telemetry or production inference. Hosted tests and custody verification are pending.
