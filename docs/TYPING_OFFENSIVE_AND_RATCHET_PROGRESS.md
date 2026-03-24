# Typing Offensive and Ratchet Progress

This pass focuses on high-value mature surfaces linked to trust/federation runtime behavior, observatory dashboard/status aggregation, and drift diagnostics.

## Latest pass (2026-03-24, Flask Importer Mainland Burn-Down II)

- Repo-wide `mypy .` moved from **6562** to **6414** errors (**-148** net).
- Flask-backed mainland cluster (selected `resonite_*` operator/API/dashboard/reporting routes) moved from **171** to **0** errors (**-171** in-cluster).
- Dominant error-family reductions from this pass:
  - `return-value`: **208 → 87** (**-121**)
  - `call-overload`: **216 → 167** (**-49**)
- Added a shared typed request-scalar coercion helper for Flask-backed payload boundaries:
  - `resonite_flask_boundary.py` (`coerce_int`, `coerce_float`).

### Fresh density audit (Flask-backed mainland)

Highest-density remaining Flask/web/operator candidates seen before implementation:
- `dashboard_ui/api.py` (43), `sentientos/admin_server.py` (31), `api/actuator.py` (19), `experiments_api.py` (17), plus related dashboard/admin tests.

Highest-payoff stabilized set in this PR (all now zero):
- `resonite_*` Flask route modules dominated by importer-boundary fallout (`return-value` from `-> str` route annotations, and `call-overload` from `int(data.get(...))` request parsing).
- Root cause: mature route modules still annotated to return `str` despite `jsonify(...)`/`Response` returns after stronger `flask_stub` typing, plus direct `object`→`int` coercions at JSON boundaries.
- Spillover: these signatures amplified importer/mainline noise across many web/operator files despite stable runtime behavior.
- Payoff realized: one broad mechanical boundary correction eliminated the entire selected cluster at once without architectural changes.

Out-of-scope/left untouched in this pass (already previously targeted or not part of this selected mainland cone):
- Already zeroed in prior pass and intentionally left unchanged: `sentient_api.py`, `plugin_dashboard.py`, `resonite_council_law_vault_engine.py`.
- Adjacent harness/test files with independent debt (kept deferred here): `tests/test_console_dashboard.py`, `tests/test_dashboard_sse_*`, `tests/test_admin_console_auth.py`, etc.

### Per-file zero-clean results in this pass

The following files moved to zero in this pass (selected Flask-backed mainland set):
- `resonite_after_action_compiler.py`
- `resonite_agent_persona_dashboard.py`
- `resonite_cathedral_grand_commission.py`
- `resonite_cathedral_launch_beacon_broadcaster.py`
- `resonite_cathedral_outreach_demo_scroll_publisher.py`
- `resonite_ceremony_replay_engine.py`
- `resonite_consent_daemon.py`
- `resonite_council_deliberation_ceremony_scheduler.py`
- `resonite_council_resilience_stress_test_orchestrator.py`
- `resonite_event_announcer.py`
- `resonite_federation_artifact_license_broker.py`
- `resonite_federation_consent_renewal_engine.py`
- `resonite_federation_handshake_verifier.py`
- `resonite_festival_anniversary_ritual_scheduler.py`
- `resonite_festival_memory_capsule_exporter.py`
- `resonite_guest_agent_consent_feedback_wizard.py`
- `resonite_law_consent_ballot_box.py`
- `resonite_manifesto_publisher.py`
- `resonite_onboarding_simulator.py`
- `resonite_public_directory_badge_issuer.py`
- `resonite_public_feedback_portal.py`
- `resonite_public_law_artifact_changelog_notifier.py`
- `resonite_public_outreach_announcer.py`
- `resonite_ritual_breach_response_system.py`
- `resonite_ritual_ceremony_archive_exporter.py`
- `resonite_ritual_invitation_engine.py`
- `resonite_ritual_rehearsal_engine.py`
- `resonite_ritual_timeline_composer.py`
- `resonite_sanctuary_emergency_posture_engine.py`
- `resonite_spiral_artifact_license_access_controller.py`
- `resonite_spiral_artifact_provenance_mapper.py`
- `resonite_spiral_bell_of_pause.py`
- `resonite_spiral_council_grand_audit_suite.py`
- `resonite_spiral_council_quorum_enforcer.py`
- `resonite_spiral_council_role_privilege_auditor.py`
- `resonite_spiral_federation_breach_analyzer.py`
- `resonite_spiral_federation_heartbeat_monitor.py`
- `resonite_spiral_festival_choreographer.py`
- `resonite_spiral_integrity_watchdog.py`
- `resonite_spiral_law_indexer.py`
- `resonite_spiral_memory_capsule_registry.py`
- `resonite_spiral_presence_proof_engine.py`
- `resonite_spiral_recovery_suite.py`
- `resonite_spiral_world_federation_census_engine.py`
- `resonite_version_diff_viewer.py`
- `resonite_world_health_mood_analytics.py`
- `resonite_world_health_mood_dashboard.py`
- `resonite_world_provenance_map_explorer.py`

## Previous pass (2026-03-23, Offensive IX)

- Comprehensive high-density offensive summary is recorded in `docs/TYPING_OFFENSIVE_PROGRESS.md`.
- Repo-wide `python -m mypy . --show-error-codes --no-error-summary` moved from **8865** to **8690** error lines in this pass (**-175**).
- Corridor files reduced to zero in this pass:
  - `architect_daemon.py`
  - `tests/test_runtime_shell.py`

## Scope of this offensive

- Broad Flask-backed operator/API/dashboard/reporting mainland burn-down across mature `resonite_*` route modules.
- Request/response boundary hardening via typed route returns (`ViewReturn`) and explicit JSON scalar coercion helpers.

## Ratchet posture

- **No debt hiding**: remaining global `mypy scripts/ sentientos/` debt remains visible.
- **No standards loosening**: no ratchet baseline expansion was used to mask errors.
- **Improved protected-surface readiness**: selected trust/observability modules are now clean and better candidates for future stricter ratchet coverage.

## Deferred debt policy

Deferred typing/runtime debt is acceptable only when:

- it is not in protected corridor paths,
- it is clearly classified by machine-readable outputs,
- and it does not degrade enforcement signals for trust, epoch, quorum, digest, or contradiction/release gates.

## Next pass recommendation

- Remaining high-density Flask/web operator hotspots: `dashboard_ui/api.py`, `sentientos/admin_server.py`, `api/actuator.py`, and `experiments_api.py`.
- Adjacent dashboard/auth test-harness typing corridor once those API surfaces are stabilized.
