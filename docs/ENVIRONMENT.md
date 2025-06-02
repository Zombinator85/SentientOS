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

