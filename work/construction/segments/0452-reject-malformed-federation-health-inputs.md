# Sequence 452 — Reject malformed Federation Health inputs

**Construction status: bounded log-input defects are corrected and queued for exact-head hosted verification.** The report parser previously assumed every valid JSON line was a mapping and every peer key was hashable. A scalar/list JSON row or an unhashable peer could abort report generation. The time-window argument also accepted zero or negative values, producing a misleading “last -N hours” report.

The source now skips non-object JSON rows, malformed payloads, and rows whose peer key cannot be added to the deterministic node set. It rejects non-positive windows with a clear `ValueError`. Regressions cover scalar/list rows, malformed nested payloads, unhashable peers, and zero/negative windows. Valid event counting, report source labels, bounded privilege gates, and publication authority remain unchanged.

This increment makes no live-telemetry or production-inference claim. The earlier receipt-bearing push run remains distinct from the still-pending scheduled execution. The preceding sequence-451 merge passed its exact-head hosted matrix; this source correction awaits its own full gate.
