# Maintenance activation profiles

`scripts/maintenance_activation_profiles.py` turns one closed, versioned operator
manifest into the standing grant, selector policy, local-Codex foreman policy,
validation policy, and landing policy consumed by the maintenance activation CLI.
It also writes an index binding every artifact's filename, schema, identity, and
digest. Rendering is deterministic metadata construction: it is **not** operator
consent, authentication, self-grant, candidate admission, activation, scheduler
installation, or execution of Codex, validation, Git, or publication.

## One-manifest workflow

1. Run `write-manifest-template --output /external/path/manifest.json` and review
   the explicitly non-authoritative template.
2. Replace every placeholder and set `template_no_authority` to `false`; seal
   `manifest_digest` over canonical JSON with that field omitted.
3. Run `render-profile-bundle --manifest ...`. The selected output directory must
   be private, external to the repository and `.git`, and free of symlinks.
4. Run `verify-profile-bundle --manifest ... --evaluation-time ...`, then use
   `inspect-profile-bundle` to review the exact validity window, scope, authority,
   budgets, landing mode, identities, and digests. Only `profile_bundle_ready` is
   readiness; warnings or blocked output are not.
5. Run `print-activation-plan`. Review its five structured argv arrays, then pass
   them deliberately to the existing `maintenance_loop_activation.py` CLI. The
   profile tool never executes those arrays or installs a scheduler.

Exact retries reuse identical bytes. Existing conflicting bytes, tampering,
cross-document disagreement, expired authority, an unsafe output root, or a
symlink fail closed.

## Decisions that must be explicit

The operator must choose the manifest ID; repository identity and absolute root;
exact base SHA; candidate kinds; allowed prefixes; forbidden patterns; every
authority class (there is no default or “all”); file, changed-line,
implementation, validation, wall-clock, attempt, corrective-retry, activation
action, and publication-backoff budgets; operator and approval references;
not-before and expiry timestamps; absolute state, workspace, scratch, inbox, and
`CODEX_HOME` paths; absolute Codex, Git, and Python executables; every validation
bound; landing mode and its mode-specific authority, executable, remote, and ref
fields; commit author/committer identity reference and title prefix; and the absolute
output directory.


## Landing-mode requirements

Remote `fast_forward_base_ref` and `pull_request` profiles retain the remote-read,
remote-publication, ref, and publication-client requirements imposed by their landing
policy; pull-request mode additionally retains PR publication authority. An absolute
`publication_client_executable` is therefore required only when the selected remote mode
uses it.

`local_fast_forward_base_ref` is deliberately local-only. Its standing grant must include
both `repository_commit` and `local_repository_base_advance`, its `tracked_base_ref` must
exactly equal `base_ref`, and the profile rejects `remote_repository_read`,
`remote_ref_publish`, and `pull_request_publish`. It may omit
`publication_client_executable` and does not require a configured Git remote. These
constraints do not grant either required local authority: the rendered profile merely
binds operator-authored configuration metadata for later verification and activation.

The schema admits no credential or secret fields and captures no environment
values. Executable paths identify programs; the tool neither authenticates them
nor reads credential bytes. Authority and scope remain exactly those authored by
the operator and are cross-checked across the canonical artifacts.
