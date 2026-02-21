.PHONY: lock lock-install docs docs-live ci rehearse audit perf
.PHONY: package package-windows package-mac
.PHONY: audit-baseline audit-drift audit-verify
.PHONY: pulse-baseline pulse-drift perception-baseline perception-drift perception-audio perception-vision perception-gaze self-baseline self-drift federation-baseline federation-drift
.PHONY: vow-manifest vow-verify vow-artifacts verify-audits-strict audit-repair audit-chain-doctor audit-accept contract-drift contract-baseline contract-status embodied-status forge-ci mypy-forge mypy-ratchet mypy-refresh-baseline mypy-touched

PYTHON ?= python3

lock:
	python -m scripts.lock freeze

lock-install:
	python -m scripts.lock install

docs:
	sphinx-build -b html docs docs/_build/html

docs-live:
	sphinx-autobuild docs docs/_build/html

rehearse: REHEARSE_ARGS := $(filter-out $@,$(MAKECMDGOALS))
rehearse:
	./scripts/rehearse.sh $(if $(REHEARSE_ARGS),$(REHEARSE_ARGS),2)

perf:
	./scripts/perf_smoke.sh

autonomy-readiness:
	$(PYTHON) tools/autonomy_readiness.py

audit-log:
	$(PYTHON) tools/autonomy_audit_cli.py --limit 50

session-dump:
	$(PYTHON) tools/session_state.py dump

session-clear:
	$(PYTHON) tools/session_state.py clear

panic-on:
	$(PYTHON) tools/panic_flag.py on

panic-off:
	$(PYTHON) tools/panic_flag.py off

reset-mood:
	$(PYTHON) tools/mood_cli.py reset

audit:
	./scripts/metrics_snapshot.sh
	./scripts/hungry_eyes_retrain.sh
	./scripts/scan_secrets.sh
	./scripts/alerts_snapshot.sh
	python scripts/generate_sbom.py
	python -c "from sentientos.config import load_runtime_config; load_runtime_config(); print('config-ok')"

full-suite:
	$(PYTHON) tools/autonomy_readiness.py --quiet
	$(PYTHON) -m scripts.run_tests -q

package:
	python scripts/package_launcher.py

package-windows:
	python scripts/package_launcher.py --platform windows

package-mac:
	python scripts/package_launcher.py --platform mac

ci:
	./scripts/ci.sh
	./scripts/verify_provenance.sh

audit-baseline:
	$(PYTHON) -m scripts.capture_audit_baseline logs $(if $(ACCEPT_MANUAL),--accept-manual,)

audit-drift:
	$(PYTHON) -m scripts.detect_audit_drift logs
	$(PYTHON) -c "import json;from pathlib import Path;p=Path('glow/audits/audit_drift_report.json');r=json.loads(p.read_text(encoding='utf-8'));print(f'drift_type={r.get(\"drift_type\", \"unknown\")}');print(f'drift_explanation={r.get(\"drift_explanation\", \"\")}')"

audit-verify:
	$(MAKE) vow-artifacts
	@MANIFEST=$$( [ -f /vow/immutable_manifest.json ] && echo /vow/immutable_manifest.json || echo vow/immutable_manifest.json ); \
	$(PYTHON) -m scripts.audit_immutability_verifier --manifest $$MANIFEST

pulse-baseline:
	$(PYTHON) -m scripts.capture_pulse_schema_baseline

pulse-drift:
	$(PYTHON) -m scripts.detect_pulse_schema_drift
	$(PYTHON) -c "import json;from pathlib import Path;p=Path('glow/pulse/pulse_schema_drift_report.json');r=json.loads(p.read_text(encoding='utf-8'));print(f'drift_type={r.get(\"drift_type\", \"unknown\")}');print(f'drift_explanation={r.get(\"drift_explanation\") or r.get(\"explanation\", \"\")}')"

perception-baseline:
	$(PYTHON) -m scripts.capture_perception_schema_baseline

perception-drift:
	$(PYTHON) -m scripts.detect_perception_schema_drift
	$(PYTHON) -c "import json;from pathlib import Path;p=Path('glow/perception/perception_schema_drift_report.json');r=json.loads(p.read_text(encoding='utf-8'));print(f'drift_type={r.get(\"drift_type\", \"unknown\")}');print(f'drift_explanation={r.get(\"drift_explanation\") or r.get(\"explanation\", \"\")}')"

self-baseline:
	$(PYTHON) -m scripts.capture_self_model_baseline

self-drift:
	$(PYTHON) -m scripts.detect_self_model_drift
	$(PYTHON) -c "import json;from pathlib import Path;p=Path('glow/self/self_model_drift_report.json');r=json.loads(p.read_text(encoding='utf-8'));print(f'drift_type={r.get(\"drift_type\", \"unknown\")}');print(f'drift_explanation={r.get(\"drift_explanation\") or r.get(\"explanation\", \"\")}')"

federation-baseline:
	$(PYTHON) -m scripts.capture_federation_identity_baseline

federation-drift:
	$(PYTHON) -m scripts.detect_federation_identity_drift
	$(PYTHON) -c "import json;from pathlib import Path;p=Path('glow/federation/federation_identity_drift_report.json');r=json.loads(p.read_text(encoding='utf-8'));print(f'drift_type={r.get(\"drift_type\", \"unknown\")}');print(f'drift_explanation={r.get(\"drift_explanation\") or r.get(\"explanation\", \"\")}')"


verify-audits-strict:
	$(PYTHON) scripts/verify_audits.py --strict

audit-repair:
	$(PYTHON) scripts/reconcile_audits.py --repair

audit-chain-doctor:
	$(PYTHON) scripts/audit_chain_doctor.py --diagnose-only

audit-accept:
	@if [ "$$SENTIENTOS_AUDIT_ACCEPT_DRIFT" != "1" ]; then echo "SENTIENTOS_AUDIT_ACCEPT_DRIFT=1 required"; exit 2; fi
	$(PYTHON) scripts/reconcile_audits.py --accept-drift

vow-artifacts:
	$(PYTHON) -m sentientos.vow_artifacts ensure

vow-manifest:
	@if [ -d /vow ] || mkdir -p /vow 2>/dev/null; then \
		$(PYTHON) -m scripts.generate_immutable_manifest --manifest /vow/immutable_manifest.json; \
	else \
		mkdir -p vow; \
		$(PYTHON) -m scripts.generate_immutable_manifest --manifest vow/immutable_manifest.json; \
	fi

vow-verify:
	$(MAKE) vow-artifacts
	@MANIFEST=$$( [ -f /vow/immutable_manifest.json ] && echo /vow/immutable_manifest.json || echo vow/immutable_manifest.json ); \
	$(PYTHON) -m scripts.audit_immutability_verifier --manifest $$MANIFEST

contract-drift:
	$(MAKE) vow-artifacts
	$(PYTHON) -m scripts.contract_drift

contract-baseline:
	$(PYTHON) -m scripts.capture_audit_baseline logs $(if $(ACCEPT_MANUAL),--accept-manual,)
	$(PYTHON) -m scripts.capture_pulse_schema_baseline
	$(PYTHON) -m scripts.capture_perception_schema_baseline
	$(PYTHON) -m scripts.capture_self_model_baseline
	$(PYTHON) -m scripts.capture_federation_identity_baseline

contract-status:
	$(PYTHON) -m scripts.emit_contract_status


forge-ci:
	$(MAKE) vow-artifacts
	$(MAKE) contract-drift
	$(MAKE) contract-status
	$(PYTHON) -m sentientos.forge run "forge_smoke_noop"

mypy-forge:
	$(PYTHON) -m mypy --strict --follow-imports=skip sentientos/cathedral_forge.py sentientos/forge_progress.py sentientos/forge.py sentientos/forge_cli/main.py sentientos/forge_cli/context.py sentientos/forge_cli/types.py sentientos/forge_cli/commands_queue.py sentientos/forge_cli/commands_sentinel.py sentientos/forge_cli/commands_train.py sentientos/forge_cli/commands_env_cache.py sentientos/forge_cli/commands_observatory.py sentientos/forge_cli/commands_provenance.py sentientos/forge_cli/commands_canary.py sentientos/forge_daemon.py sentientos/forge_queue.py sentientos/forge_index.py sentientos/forge_status.py sentientos/contract_sentinel.py sentientos/forge_progress_contract.py sentientos/forge_campaigns.py sentientos/forge_provenance.py sentientos/forge_replay.py sentientos/audit_reconcile.py sentientos/audit_doctor.py sentientos/audit_chain_gate.py sentientos/github_artifacts.py

speak:
	$(PYTHON) sosctl.py say "$(if $(MSG),$(MSG),Hello from SentientOS)"

asr-smoke:
	$(PYTHON) sosctl.py asr-smoke $(if $(SECONDS),--seconds $(SECONDS),) $(if $(AMP),--amplitude $(AMP),)

screen-ocr-smoke:
	$(PYTHON) sosctl.py screen-ocr-smoke --text "$(if $(TEXT),$(TEXT),screen smoke test)" $(if $(TITLE),--title "$(TITLE)",)

social-smoke:
	$(PYTHON) sosctl.py social-smoke $(if $(URL),$(URL),https://example.com) $(if $(ACTION),--action $(ACTION),) $(if $(SELECTOR),--selector "$(SELECTOR)",) $(if $(TEXT),--text "$(TEXT)",)

%:
	@:

perception-audio:
	$(PYTHON) -m scripts.perception.audio_adapter --privacy-class internal --window-ms 500 --iterations 1

perception-vision:
	$(PYTHON) -m scripts.perception.vision_adapter --privacy-class internal --iterations 1

perception-gaze:
	$(PYTHON) -m scripts.perception.gaze_adapter --privacy-class internal --iterations 1

embodied-status:
	$(MAKE) contract-drift
	$(MAKE) contract-status
	$(PYTHON) -c "import json;from pathlib import Path;f=Path('glow/contracts/contract_status.json');p=json.loads(f.read_text(encoding='utf-8'));print('[embodied-status] contract_status='+str(f));print('[embodied-status] domains='+str(len(p.get('contracts', []))))"


mypy-ratchet:
	$(PYTHON) scripts/mypy_ratchet.py

mypy-refresh-baseline:
	@if [ "$$SENTIENTOS_ALLOW_BASELINE_REFRESH" != "1" ]; then echo "SENTIENTOS_ALLOW_BASELINE_REFRESH=1 required"; exit 2; fi
	$(PYTHON) scripts/mypy_ratchet.py --refresh

mypy-touched:
	$(PYTHON) scripts/mypy_ratchet.py --touched-surface
