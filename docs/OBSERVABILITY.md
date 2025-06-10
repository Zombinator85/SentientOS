# Observability

When deployed on Kubernetes, SentientOS exposes Prometheus metrics on port 9100. If you use the `kube-prometheus-stack`, create a `ServiceMonitor` pointing at the `sentientos` service to scrape metrics.

Each request increments `sentientos_tenant_requests_total{tenant="..."}` and updates `sentientos_tenant_cost_usd{tenant="..."}`. Use Grafana filters with `{{ tenant }}` in the legend to view per-tenant usage.
