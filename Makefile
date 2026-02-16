.PHONY: lock lock-install docs docs-live ci rehearse audit perf
.PHONY: package package-windows package-mac
.PHONY: audit-baseline audit-drift audit-verify

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
	$(PYTHON) -m scripts.audit_immutability_verifier

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
