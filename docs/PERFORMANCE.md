# Performance

Initial locust run using `bench/locustfile.py` at 100 users for 30 seconds produced a 95th percentile latency under 250ms on a local machine. The CI performance check fails the build if p95 exceeds 250ms.
