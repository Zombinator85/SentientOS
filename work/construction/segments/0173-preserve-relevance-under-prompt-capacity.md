## 2026-10-13 checkpoint — preserve task relevance when prompt capacity shrinks

- Continued from source commit `32c1291a481416b207a8f6947f3f959df8982970` (tree `615c8439fc9607690c4498b982ed9973d0421059`); published source commit `205a84168a4128df5cfbbb36435970481e1e5343` (tree `c3e346bc429e228b186ca345adbb986ad08b6607`).
- Review found that ranking records by probe overlap was insufficient while returning them in checkpoint order: the prompt binder admits complete suffixes, so a tighter budget could drop an older, higher-overlap record. The selected bounded set is now ordered from lower to higher overlap, with checkpoint recency breaking ties. Every smaller complete suffix therefore preserves the strongest ranked records first. Non-family filler remains below family matches.
- The affected five-test bundle passed after this change: task-family example flow, adverse history, receipt-bound progression, exact-family staging, and invariant history comparison. Python compilation and `git diff --check` passed. Independent fetch confirmed the published tree and changed source blob.
- The test evidence remains fixture based; no actual model behavior, production verification, or performance improvement is claimed.

Next: add an explicit saturated-budget adversarial case with overlapping positive and adverse records, then verify the omitted-history manifest and progression lineage after restart.
