.PHONY: lock lock-install docs docs-live ci rehearse audit perf
.PHONY: package package-windows package-mac
.PHONY: audit-baseline audit-drift audit-verify
.PHONY: pulse-baseline pulse-drift perception-baseline perception-drift self-baseline self-drift federation-baseline federation-drift
.PHONY: vow-manifest vow-verify contract-drift contract-baseline contract-status

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
	@if [ "$(NO_GENERATE)" != "1" ]; then $(MAKE) vow-manifest; fi
	$(PYTHON) -m scripts.audit_immutability_verifier --manifest /vow/immutable_manifest.json

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

vow-manifest:
	mkdir -p /vow
	$(PYTHON) -m scripts.generate_immutable_manifest --manifest /vow/immutable_manifest.json

vow-verify:
	@if [ "$(NO_GENERATE)" != "1" ]; then $(MAKE) vow-manifest; fi
	$(PYTHON) -m scripts.audit_immutability_verifier --manifest /vow/immutable_manifest.json

contract-drift:
	$(PYTHON) -m scripts.contract_drift

contract-baseline:
	$(PYTHON) -m scripts.capture_audit_baseline logs $(if $(ACCEPT_MANUAL),--accept-manual,)
	$(PYTHON) -m scripts.capture_pulse_schema_baseline
	$(PYTHON) -m scripts.capture_perception_schema_baseline
	$(PYTHON) -m scripts.capture_self_model_baseline
	$(PYTHON) -m scripts.capture_federation_identity_baseline

contract-status:
	$(PYTHON) -m scripts.emit_contract_status

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
