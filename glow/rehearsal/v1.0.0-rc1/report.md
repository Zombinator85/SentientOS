# Autonomy Rehearsal Report

- Generated: 2025-11-02T15:47:42.144994Z
- Branch: work
- Candidate ID: 67fee89f-c830-4080-97f3-89fd4f562f9f

## Overview

| Tool | Version |
| --- | --- |
| cmake | cmake version 3.28.3 |
| ninja | 1.11.1 |
| python | Python 3.11.12 |
| pip | pip 25.2 from /root/.pyenv/versions/3.11.12/lib/python3.11/site-packages/pip (python 3.11) |
| pytest | pytest 7.4.4 |
| make | GNU Make 4.3 |
| git | git version 2.43.0 |

## Amendment Table

| id | topic | integrity_valid | risk_score | gates |
| --- | --- | --- | --- | --- |
| 67fee89f-c830-4080-97f3-89fd4f562f9f | stabilise scripts.lock install flow | True | 0.220 | approved |

## Latency

- Integrity: 14.38 ms
- Tests total: 8190.78 ms
- CI (make ci): 4338.52 ms
- Median stage latency: 4338.52 ms
- P95 stage latency: 8190.78 ms

## Risk Distribution

- Bucket 0.2-0.3 : 1 amendment

## Quarantines

- Count: 0

## Diff Summary

- scripts/lock.py: consolidate docstring, normalise import order, and retain privilege gating

## CI Outcome

- pytest -q returncode: 0
- make ci returncode: 0

## Regressions

- none detected

## Next Steps

1. Expand rehearsal harness to ingest multiple amendments per cycle.
2. Capture raw stdout/stderr artifacts for each gate in future rehearsals.
3. Integrate remote CI status polling into the timeline emitter.
