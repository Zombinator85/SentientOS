.PHONY: lock lock-install docs docs-live ci rehearse audit
.PHONY: package package-windows package-mac

lock:
	python -m scripts.lock freeze

lock-install:
	python -m scripts.lock install

docs:
	sphinx-build -b html docs docs/_build/html

docs-live:
	sphinx-autobuild docs docs/_build/html

rehearse:
	./scripts/rehearse.sh 2

audit:
	./scripts/metrics_snapshot.sh
	./scripts/hungry_eyes_retrain.sh
	python -c "from sentientos.config import load_runtime_config; load_runtime_config(); print('config-ok')"

package:
	python scripts/package_launcher.py

package-windows:
	python scripts/package_launcher.py --platform windows

package-mac:
	python scripts/package_launcher.py --platform mac

ci:
	./scripts/ci.sh
	./scripts/verify_provenance.sh
