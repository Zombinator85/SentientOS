# Environment Variables

SentientOS tools read configuration from `.env`. Copy `.env.example` to `.env` and update the values as needed.
The table below explains each variable and its default behavior.

| Variable | Purpose | Default |
| --- | --- | --- |
| `RELAY_SECRET` | Shared secret for relay authentication | *(no default)* |
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
| `EDITOR` | Fallback editor for workflow tools | `nano` |
| `EMERGENCY_STATE` | Lock file indicating emergency mode | `state/emergency.lock` |
| `EMO_VIS_HOST` | Host for emotion visualizer | `0.0.0.0` |
| `EMO_VIS_PORT` | Port for emotion visualizer | `9000` |
| `FEEDBACK_NO_PROMPT` | Disable prompt during feedback capture | *(unset)* |
| `FINAL_APPROVER_FILE` | JSON file listing final approvers | `config/final_approvers.json` |
| `GENESIS_ORACLE_DATA` | Directory for genesis oracle data | `logs` |
| `GITHUB_TOKEN` | GitHub token for CLI utilities | *(none)* |
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
| `OCR_WATCH` | Folder watched for OCR screenshots | `screenshots` |
| `PORT` | HTTP port for the blessing ceremony API | `5000` |
| `REQUIRED_FINAL_APPROVER` | Default final approver nickname | `4o` |
| `RITUAL_BUNDLE_DIR` | Location for ritual bundles | `bundles` |
| `SELF_REFLECTION_QUESTION` | Prompt used by self‑reflection logger | `What have you learned recently?` |
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
| `WEBHOOK_CHECK_SEC` | Seconds between webhook status checks | `60` |
| `WORKFLOW_REVIEW_DIR` | Directory for submitted workflow reviews | `workflows/review` |

