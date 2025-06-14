# Experimental Feature Flags

SentientOS includes several prototypes that are disabled by default. Enable them by setting the corresponding environment variable to `1`.

| Variable | Description | Default |
|----------|-------------|---------|
| `EXPERIMENT_TRUST_SCORING` | Enable trust score logging | *(unset)* |
| `TRUST_SCORE_LOG` | Path for trust score log | `logs/trust_scores.jsonl` |
| `EXPERIMENT_PRESENCE_ANALYTICS` | Enable presence analytics logging | *(unset)* |
| `PRESENCE_ANALYTICS_LOG` | Path for presence analytics log | `logs/presence_analytics.jsonl` |
| `EXPERIMENT_SELF_HEAL_PLUGIN` | Enable the self-healing demo plugin | *(unset)* |
| `SELF_HEAL_PLUGIN_LOG` | Path for self-healing plugin log | `logs/self_heal_plugin.jsonl` |

These experimental features may change without notice. Keep their logs private unless your node has been blessed for public federation.
