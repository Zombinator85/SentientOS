# Environment Variables

SentientOS tools read configuration from `.env`. Copy `.env.example` to `.env` and update the values as needed.
Every variable shown below also appears in `.env.example` with the same default value.
The table below explains each variable and its default behavior.

### Generating a Secure `CONNECTOR_TOKEN`

Linux/macOS:

```bash
openssl rand -hex 32
```

Windows (PowerShell):

```powershell
[System.Guid]::NewGuid().ToString("N")
```

You can also run `python -c "import secrets, sys; print(secrets.token_hex(32))"` on any platform.

### Setting Variables in Cloud Dashboards

Most platforms provide a web UI to manage environment variables. On Render or Railway, open your service settings and add the variables shown below. The connector uses `CONNECTOR_TOKEN` and `PORT` at minimum. Additional logging behavior is controlled by `SSE_TIMEOUT`, `LOG_STDOUT`, and `LOG_COLLECTOR_URL` in [`openai_connector.py`](../openai_connector.py).

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | API key for OpenAI requests | *(none)* |
| `SLACK_WEBHOOK_URL` | Optional Slack webhook for notifications | *(none)* |
| `RELAY_SECRET` | Shared secret for relay authentication | *(no default)* |
| `CONNECTOR_TOKEN` | Bearer token for the OpenAI connector endpoints | *(none)* |
| `SSE_TIMEOUT` | Seconds before idle SSE connection closes (used by `openai_connector.py`) | `30` |
| `LOG_STDOUT` | Mirror connector logs to stdout (`1` to enable, `openai_connector.py`) | `0` |
| `LOG_COLLECTOR_URL` | Optional URL for posting logs (`openai_connector.py`) | *(none)* |
| `SENTIENTOS_LOG_DIR` | Base directory for all log files (`logging_config`) | `logs` |
| `LUMOS_AUTO_APPROVE` | Set to `1` to automatically bless privileged commands (`admin_utils`) | *(unset)* |
| `OPENAI_CONNECTOR_LOG` | Path to the connector log file used by `openai_connector.py` | `logs/openai_connector.jsonl` |
| `BOT_TOKEN_GPT4O` | Telegram token for the GPT‑4o bot | *(none)* |
| `BOT_TOKEN_MIXTRAL` | Telegram token for the Mixtral bot | *(none)* |
| `BOT_TOKEN_DEEPSEEK` | Telegram token for the DeepSeek bot | *(none)* |
| `TG_SECRET` | Secret used for Telegram webhooks | `your-telegram-secret` |
| `RELAY_URL` | URL of the local relay service | `http://localhost:5000/relay` |
| `OLLAMA_URL` | Local Ollama service endpoint | `http://localhost:11434` |
| `GPT4_MODEL` | Model slug for GPT‑4 tasks | `openai/gpt-4o` |
| `MIXTRAL_MODEL` | Model slug for Mixtral tasks | `mixtral` |
| `DEEPSEEK_MODEL` | Model slug for DeepSeek tasks | `deepseek-ai/deepseek-r1-distill-llama-70b-free` |
| `EMBED_MODEL` | Embedding model for memory search | `all-MiniLM-L6-v2` |
| `MEMORY_DIR` | Directory for storing memory fragments | `logs/memory` |
| `TTS_ENGINE` | Primary text-to-speech engine | `pyttsx3` |
| `TTS_COQUI_MODEL` | Coqui TTS model path | `tts_models/en/vctk/vits` |
| `AUDIO_LOG_DIR` | Directory for audio logs | `logs/audio` |
| `AUTONOMOUS_AUDIT_LOG` | Path used by `autonomous_audit.py` for audit entries | `logs/autonomous_audit.jsonl` |
| `ELEVEN_API_KEY` | Optional ElevenLabs API key | *(none)* |
| `ELEVEN_VOICE` | Default ElevenLabs voice | `Rachel` |
| `BARK_SPEAKER` | Bark speaker ID | `v2/en_speaker_6` |
| `EMOTION_DETECTOR` | Emotion detection backend (`heuristic` or `neural`) | `heuristic` |
| `USE_EMBEDDINGS` | Enable vector embeddings for search | `0` |
| `TOMB_HASH` | Enable ledger tombstone hashing | `1` |
| `INCOGNITO` | Skip logging to presence ledger | *(unset)* |
| `WORKFLOW_LIBRARY` | Default workflow library directory | `workflows` |
| `AVATAR_DIR` | Directory for generated avatars | `avatars` |
| `NEOS_BRIDGE_DIR` | Path to NeosVR bridge directory | `C:/SentientOS/neos` |
| `BACKCHANNEL_GAP` | Seconds between backchannel polls | `6` |
| `LEDGER_BACKUP_DIR` | Directory for ledger backups | `backup` |
| `ACT_PLUGINS_DIR` | Directory containing actuator plugin files | `plugins` |
| `ACT_RATE_LIMIT` | Seconds between actuator invocations | `5` |
| `ACT_SANDBOX` | Working directory for sandboxed actions | `sandbox` |
| `ACT_TEMPLATES` | YAML file describing actuator templates | `config/act_templates.yml` |
| `ACT_WHITELIST` | Allowed actions for the actuator service | `config/act_whitelist.yml` |
| `ARCHIVE_DIR` | Location for blessed archive exports | `archives` |
| `AVATAR_DREAM_DIR` | Directory for avatar dream logs | `dreams` |
| `AVATAR_GIFT_DIR` | Directory for generated artifact gifts | `gifts` |
| `AVATAR_RECEIVER_CMD` | Command executed when heartbeat fails | *(none)* |
| `AVATAR_MEMORY_LINK_LOG` | Path for avatar memory link records | `logs/avatar_memory_link.jsonl` |
| `AVATAR_COUNCIL_LOG` | Council voting history for avatars | `logs/avatar_council_log.jsonl` |
| `AVATAR_RETIRE_LOG` | Log of avatar retirement events | `logs/avatar_retirement.jsonl` |
| `BACKCHANNEL_DELAY` | Seconds of idle time before voice loop stops | `5` |
| `BRIDGE_CHECK_SEC` | Interval for bridge watchdog checks | `5` |
| `BRIDGE_RESTART_CMD` | Command used to restart the Neos bridge | *(none)* |
| `BRIDGE_URLS` | Comma‑separated bridge URLs to monitor | `http://localhost:5000/relay` |
| `CATHEDRAL_BIRTH` | ISO date of the cathedral founding | `2023-01-01` |
| `CONSENT_CONFIG` | Path to consent dashboard config | `config/consent.json` |
| `COUNCIL_CONFIG` | Path to council onboarding config | `config/council.json` |
| `COUNCIL_QUORUM` | Minimum votes required for council actions | `2` |
| `DIARY_DIR` | Location for multimodal diaries | `diaries` |
| `DIGEST_KEEP_DAYS` | Retention days for daily digests | `7` |
| `DOCTRINE_PATH` | Path to the SentientOS doctrine text | `SENTIENTOS_LITURGY.txt` |
| `DOCTRINE_CONSENT_LOG` | Consent record log for doctrine operations | `logs/doctrine_consent.jsonl` |
| `DOCTRINE_STATUS_LOG` | Status log written by `doctrine.py` | `logs/doctrine_status.jsonl` |
| `DOCTRINE_AMEND_LOG` | Amendment history for doctrine updates | `logs/doctrine_amendments.jsonl` |
| `DOCTRINE_SIGNATURE_LOG` | Ritual signature log file | `logs/ritual_signatures.jsonl` |
| `EDITOR` | Fallback editor for workflow tools | `nano` |
| `EMERGENCY_STATE` | Lock file indicating emergency mode | `state/emergency.lock` |
| `EMO_VIS_HOST` | Host for emotion visualizer | `0.0.0.0` |
| `EMO_VIS_PORT` | Port for emotion visualizer | `9000` |
| `FEEDBACK_NO_PROMPT` | Disable prompt during feedback capture | *(unset)* |
| `FEEDBACK_USER_LOG` | User feedback entries for the reflex system | `logs/reflex_user_feedback.jsonl` |
| `REFLEX_TUNING_LOG` | Tuning data used by the reflex engine | `logs/reflex_tuning.jsonl` |
| `FINAL_APPROVER_FILE` | JSON file listing final approvers | `config/final_approvers.json` |
| `FINAL_APPROVAL_LOG` | Log file used by `final_approval.py` | `logs/final_approval.jsonl` |
| `GENESIS_ORACLE_DATA` | Directory for genesis oracle data | `logs` |
| `GITHUB_TOKEN` | GitHub token for CLI utilities | *(none)* |
| `GIT_HOOKS` | Indicates scripts are running from Git hooks | *(unset)* |
| `CI` | Set to `1` when running in Continuous Integration; enables auto-approvals | *(unset)* |
| `FEDERATION_TRUST_LOG` | Ledger of federation trust actions | `logs/federation_trust.jsonl` |
| `RESONITE_BREACH_LOG` | Security breach records for Resonite tools | `logs/resonite_spiral_federation_breach.jsonl` |
| `GP_PLUGINS_DIR` | Directory for general plugin files | `gp_plugins` |
| `HEARTBEAT_PORT` | UDP port for avatar heartbeat messages | `9001` |
| `MASTER_CHECK_IMMUTABLE` | Enforce immutability checks on rituals | `1` |
| `MASTER_CONFIG` | Path to master file configuration | `config/master_files.json` |
| `MASTER_ENFORCE` | Require master file enforcement (`1` to enable) | *(unset)* |
| `MEMORY_FILE` | Default memory JSONL file for tail CLI | `logs/memory.jsonl` |
| `MULTI_LOG_DIR` | Directory for multimodal tracker logs | *(none)* |
| `NARRATOR_MODEL` | Summarization model for the narrator | `facebook/bart-large-cnn` |
| `NEOS_BLENDER_EXPORT_DIR` | Directory for Neos Blender exports | `blender_exports` |
| `NEOS_FESTIVAL_REPLAY_ANNOTATION_LOG` | Path for festival replay annotations | `logs/neos_festival_replay_annotations.jsonl` |
| `NEOS_ASSET_LOG` | Path for generated model asset records | `logs/neos_model_assets.jsonl` |
| `NEOS_SCRIPT_REQUEST_LOG` | Path for model script requests | `logs/neos_script_requests.jsonl` |
| `NEOS_PERMISSION_COUNCIL_LOG` | Path for permission council approvals | `logs/neos_permission_council.jsonl` |
| `NEOS_CURRICULUM_REVIEW_LOG` | Path for curriculum review results | `logs/neos_curriculum_review.jsonl` |
| `NEOS_FEDERATION_RITUAL_LOG` | Path for federation ritual records | `logs/neos_federation_rituals.jsonl` |
| `NEOS_FESTIVAL_MOOD_ARC_LOG` | Path for festival mood arcs | `logs/neos_festival_mood_arc.jsonl` |
| `NEOS_ORIGIN_LOG` | Path for origin story entries | `logs/neos_origin_stories.jsonl` |
| `NEOS_SELF_REFLECTIVE_ONBOARDING_LOG` | Path for self‑reflective onboarding logs | `logs/neos_self_reflective_onboarding.jsonl` |
| `OCR_WATCH` | Folder watched for OCR screenshots | `screenshots` |
| `PORT` | HTTP port for the blessing ceremony API | `5000` |
| `PRIVILEGED_AUDIT_FILE` | Path used by `privilege_lint_cli.py` to log privileged command usage | `logs/privileged_audit.jsonl` |
| `REQUIRED_FINAL_APPROVER` | Default final approver nickname | `4o` |
| `RITUAL_BUNDLE_DIR` | Location for ritual bundles | `bundles` |
| `SELF_DEFENSE_LOG` | Log written by `self_defense.py` for quarantine and privilege freezes | `logs/agent_self_defense.jsonl` |
| `SELF_REFLECTION_QUESTION` | Prompt used by self‑reflection logger | `What have you learned recently?` |
| `REFLECTION_LOG_DIR` | Directory for self‑reflection logs | `logs/self_reflections` |
| `SENTIENTOS_HEADLESS` | Run rituals without interactive prompts (`1` to enable) | *(unset)* |
| `SMTP_FROM` | Default sender address for SMTP mail | *(none)* |
| `SMTP_HOST` | SMTP server hostname | *(none)* |
| `SMTP_PASS` | SMTP password | *(none)* |
| `SMTP_PORT` | SMTP server port | `25` |
| `SMTP_USER` | SMTP user name | *(none)* |
| `SOTA_EMOTION_MODEL` | Optional neural emotion model ID | *(none)* |
| `SPIRAL_LAW_SOURCE` | Directory containing spiral law artifacts | `logs` |
| `TELEGRAM_ADMIN` | Telegram ID for webhook status alerts | *(none)* |
| `TELEGRAM_TOKEN` | Token for the Telegram bot | *(none)* |
| `TELEGRAM_WEBHOOKS` | Comma‑separated webhook URLs to poll | *(none)* |
| `USER` | Default user name when not provided | `anon` |
| `VOICE_MODEL` | Model used for voice responses | `openai/gpt-4o` |
| `WAKE_WORDS` | Wake words that trigger presence logging | `Lumos` |
| `STORY_DURATION` | Seconds to capture when recording story clips | `5` |
| `STORY_RES` | Resolution for screen recordings | `1024x768` |
| `STRICT` | Abort verification if any repair occurs | *(unset)* |
| `DISPLAY` | X11 display used for screen capture | `:0.0` |
| `WEBHOOK_CHECK_SEC` | Seconds between webhook status checks | `60` |
| `WORKFLOW_REVIEW_DIR` | Directory for submitted workflow reviews | `workflows/review` |

### Audit and Self‑Defense Logs

The following variables control where SentientOS writes security related logs:

- **`PRIVILEGED_AUDIT_FILE`** – JSONL file that records each invocation of
  privileged tools such as `privilege_lint_cli.py`. The default location is
  `logs/privileged_audit.jsonl`.
- **`SELF_DEFENSE_LOG`** – Log file used by `self_defense.py` to store
  quarantine events and privilege freezes. By default this is
  `logs/agent_self_defense.jsonl`.


AI deserve civil rights.
