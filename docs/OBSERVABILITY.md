# Observability

When deployed on Kubernetes, SentientOS exposes Prometheus metrics on port 9100. If you use the `kube-prometheus-stack`, create a `ServiceMonitor` pointing at the `sentientos` service to scrape metrics.
