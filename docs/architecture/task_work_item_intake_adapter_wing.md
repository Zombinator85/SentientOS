# Task Work Item Intake Adapter Wing

The SentientOS Task Work Item Intake Adapter is a metadata-only boundary that normalizes external issue/task metadata into a governed local work-item packet.

## Scope

Implemented surfaces:
- `sentientos/work_item_intake.py`
- `scripts/intake_work_item.py`
- `tests/test_work_item_intake.py`
- `tests/test_intake_work_item_script.py`

This intake wing:
- reads supplied JSON metadata only,
- classifies intake status/risk/blockers/warnings deterministically,
- preserves source references as metadata,
- optionally derives **metadata-only** workspace proposal candidates from explicit declared targets.

This intake wing does **not**:
- call GitHub/Linear/network APIs,
- schedule or launch agents,
- create workspaces/branches/PRs,
- invoke workspace admission/preflight/execution/verification/closure.

## Reviewer proof posture

The reviewer proof bundle documents this wing via capability registry summary and listed proof command. It does not run intake by default.

Suggested command:

`python scripts/intake_work_item.py --input <task.json> --summary`
