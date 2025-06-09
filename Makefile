.PHONY: lock lock-install

lock:
	python -m scripts.lock freeze

lock-install:
	python -m scripts.lock install
