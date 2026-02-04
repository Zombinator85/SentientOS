.PHONY: lock lock-install docs docs-live ci rehearse audit perf
.PHONY: package package-windows package-mac

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
