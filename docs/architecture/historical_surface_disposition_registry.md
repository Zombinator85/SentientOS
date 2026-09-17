# Historical Surface Disposition Registry

> **File existence is not organism membership.**
>
> **Disposition metadata is descriptive evidence, not execution authority.**

The registry at [`architecture/historical_surface_dispositions.json`](../../architecture/historical_surface_dispositions.json)
makes a small, bounded set of claims about what repository surfaces currently *are*.
It supports architectural archaeology without deleting preserved work or guessing that
unexplained history is dead. The validator reads JSON and filesystem metadata only. It
does not import, execute, activate, disable, or otherwise inspect the behavior of a
classified target.

## Distinct questions

Filesystem presence says only that bytes exist. Architectural membership says how the
current project understands those bytes. Support requires separate, current evidence;
runtime reachability is a wiring fact; and authority is decided only by existing
capability, control-plane, governor, effect, maintenance, and adoption contracts. A
`canonical` disposition therefore grants no privilege, and a `retired` disposition is
not an execution-denial mechanism or deletion instruction.

Historical disposition describes what a surface is. It does not determine what that
surface is allowed to do. The registry is not consumed by runtime admission code and
contains no authority field.

## V1 dispositions and evidence

| Value | Meaning and minimum evidence |
|---|---|
| `canonical` | Part of the present primary organism; cite current wiring plus focused tests or current architecture documentation. |
| `alternate_runtime` | A distinct, coexisting runtime surface; cite its entry/wiring and current tests. This label alone does not promise official support. |
| `compatibility_only` | Retained only for a bounded compatibility contract; cite the compatibility consumer and contract. |
| `superseded` | Replaced by an identified registry record; `successor` is mandatory, must resolve, and chains must be acyclic. Reachability is not implied. |
| `operator_legacy` | A preserved utility still invoked explicitly by an operator; cite the invocation surface and current evidence. |
| `historical_experiment` | Preserved for archaeology rather than asserted current membership; cite affirmative historical evidence, not age or naming alone. |
| `retired` | Intentionally retired by affirmative repository evidence. This neither authorizes deletion nor denies execution. |
| `unknown_disposition` | Evidence is insufficient for a stronger claim. Unknown is valid and must never be silently converted to another value. |

## Records, scope, and conflicts

Each record has a stable `id`, one or more exact repository-relative `paths`, a
`disposition`, rationale, evidence `references`, optional architectural `owner`, and an
optional `successor`. Paths are exact file or directory boundaries: glob characters,
absolute paths, and parent traversal are rejected. Ancestor/descendant claims belonging
to different records overlap and fail validation. This prevents a broad directory claim
from silently classifying future descendants under a different identity.

A directory is not necessarily one architectural surface. The legacy `council/`
directory demonstrates why: its `Bus`, `Message`, and `Referee` primitives are exercised
dependencies of the WDM alternate runtime, while its standalone runner and provider-named
deterministic stubs have no equally well-evidenced terminal role. The registry therefore
uses exact file and bounded subdirectory records for those components instead of one
`council/` claim. New files beneath that directory are not classified implicitly.

`inventory_scope` is deliberately small in v1. A scoped path with no record is reported
as unclassified; a record explicitly labeled `unknown_disposition` remains unknown.
Targets that do not exist are reported as missing. Classified targets outside the
declared scope are reported as stale. Missing, stale, duplicate, conflicting, invalid,
broken-successor, and cyclic-successor conditions make validation fail.

To add or update a disposition:

1. Gather affirmative current or historical evidence; do not infer disposition from a
   filename, age, import reachability, or absence from `sentientosd`.
2. Add the exact path to `inventory_scope` and create or update one stable record.
3. Add repository-relative evidence references and a specific rationale.
4. For `superseded`, identify the successor record and validate the complete chain.
5. Run the validator and focused tests below.

## Deterministic report

```bash
python scripts/report_historical_surface_dispositions.py
python -m scripts.run_tests -q tests/test_historical_surface_disposition.py
```

The sorted JSON report includes classified, explicitly unknown, unclassified, missing,
and stale paths; validation errors; and totals for every disposition. It contains no
timestamps, performs no network/provider/model calls, mutates no runtime state, and does
not import classified Python modules.

V1 does **not** claim complete repository coverage. It does not equate static import
reachability with membership, call historical experiments safe, promise support for
alternate runtimes, declare superseded code unreachable, or authorize execution,
maintenance, adoption, runtime replacement, effects, provider use, network use, or
repository mutation.
