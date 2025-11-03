# Autonomy Metrics

The following metrics are exposed through `/admin/metrics` (Prometheus exposition format) and persisted to
`glow/metrics/autonomy.prom` as part of every rehearsal. Suggested alert thresholds are included for production deployments.

| Metric | Type | Description | Suggested Alert |
| --- | --- | --- | --- |
| `sos_curator_capsules_written_total` | Counter | Number of semantic memory capsules persisted. | Sudden drop indicates curator backlog; alert if flat for >1h. |
| `sos_reflexion_notes_total` | Counter | Count of Reflexion notes written. | Alert if zero notes while reflexion enabled for >6h. |
| `sos_critic_disagreements_total` | Counter | Critic disagreements that triggered quarantine. | Alert on rapid increase (>5 in 10m). |
| `sos_council_votes_total{result=...}` | Counter | Council voting outcomes with result label. | Alert if `result="tied"` spikes, indicating persistent quorum failures. |
| `sos_oracle_requests_total{mode=...}` | Counter | Oracle requests labelled by operating mode (`online` or `degraded`). | Alert when degraded mode appears for >2 consecutive requests. |
| `sos_goals_autocreated_total` | Counter | Automatically generated goals accepted by the curator. | Alert if exceeds policy limits. |
| `sos_hungryeyes_corpus_bytes` | Gauge | Size of the HungryEyes active learning corpus in bytes. | Alert if growth stalls (possible ingest failure) or spikes unexpectedly. |
| `sos_hungryeyes_retrains_total` | Counter | Number of active-learning retraining events. | Alert if zero for 24h when enabled. |
| `sos_reflexion_latency_ms` | Histogram | Latency per reflexion note in milliseconds. | Alert if P95 exceeds 1500ms. |
| `sos_critic_latency_ms` | Histogram | Latency per critic review in milliseconds. | Alert if P95 exceeds 2000ms. |
| `sos_oracle_latency_ms` | Histogram | Oracle round-trip latency in milliseconds. | Alert if P95 exceeds configured timeout. |

The metrics snapshot file `glow/rehearsal/latest/metrics.snap` stores the same metrics in JSON form, useful for historical
comparison during incident review.
