.PHONY: lock-refresh lock-install-bin lock-install-src

lock-refresh:
	python scripts/gen_lock.py

lock-install-bin:
	python scripts/install_locked.py bin

lock-install-src:
	python scripts/install_locked.py src
