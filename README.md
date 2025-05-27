SentientOS Scripts
This repository contains utilities and small services used to run SentientOS agents. The original code base was a single script but has been split for clarity.

Important:
All API tokens and secrets have been removed.
Copy .env.example to .env and provide your own credentials for proper operation.

Scripts / Utilities
Telegram bridges – Three Flask apps that forward Telegram messages to the relay. Each bridge talks to a different model (GPT‑4o, Mixtral, or DeepSeek) and logs all fragments through memory_manager.

relay_app.py – Minimal relay for local development and testing. It verifies a shared secret, echoes incoming text, and records it (with emotion vectors) in memory.

memory_manager.py – Persistent storage for message fragments. Each entry stores a 64‑dimensional emotion vector along with the text and is indexed for retrieval.

memory_cli.py – Command-line interface exposing cleanup, summarization, playback, and emotion timeline helpers.

memory_tail.py – Colorized log viewer for logs/memory.jsonl.

heartbeat.py – Simple client that periodically sends heartbeat pings to the relay.

cathedral_hog_wild_heartbeat.py – Demo that periodically summons multiple models via the relay.

mic_bridge.py – Captures microphone audio, converts speech to text, and infers emotions using a configurable detector (heuristic or neural). Supports fusion with vision input (image file) for multimodal emotion vectors.

tts_bridge.py – Speaks model replies aloud using a pluggable TTS engine (pyttsx3, Coqui, ElevenLabs, Bark) and adjusts rate/voice based on emotion.

voice_loop.py – Links the mic and TTS bridges for hands-free, full-duplex conversation with emotion-aware responses, persona adaptation, and interruption support. Streams replies chunk by chunk.

browser_voice.py – Minimal Flask demo for browser-based voice chat with live emotion readout, persona switching, and audio upload for emotion analysis.

rebind.rs – Rust helper that binds Telegram webhooks to the URLs reported by ngrok.

emotions.py – Canonical list of 64 emotion labels for the EPU.

api/actuator.py – Executes whitelisted shell commands, HTTP requests, file writes, emails, and webhooks with persistent logging. Patterns control what commands/URLs are allowed and all file operations are sandboxed. Also provides a CLI and powers the /act relay endpoint.

ngrok.yml – Example ngrok configuration.

Environment Variables
Create a .env file based on .env.example and set the following variables:

Variable	Purpose
RELAY_SECRET	Shared secret used by the relay and all bridges
OPENROUTER_API_KEY	API key for GPT‑4o calls
TOGETHER_API_KEY	API key for DeepSeek calls
BOT_TOKEN_GPT4O	Telegram token for the GPT‑4o bridge
BOT_TOKEN_MIXTRAL	Telegram token for the Mixtral bridge
BOT_TOKEN_DEEPSEEK	Telegram token for the DeepSeek bridge
TG_SECRET	Telegram webhook secret
RELAY_URL	URL of the relay service
OLLAMA_URL	Local Ollama endpoint
GPT4_MODEL	Model slug for GPT‑4o
MIXTRAL_MODEL	Model slug for Mixtral
DEEPSEEK_MODEL	Model slug for DeepSeek
EMBED_MODEL	Embedding model for memory search
MEMORY_DIR	Directory used for persistent memory
TTS_ENGINE	"pyttsx3" (default), "coqui", "elevenlabs", or "bark"
TTS_COQUI_MODEL	Coqui model when TTS_ENGINE=coqui
ELEVEN_API_KEY	API key for ElevenLabs (optional)
ELEVEN_VOICE	Voice ID for ElevenLabs
BARK_SPEAKER	Speaker preset for Bark
AUDIO_LOG_DIR	Directory for recorded audio files
EMOTION_DETECTOR	"heuristic" (default) or "neural"
ACT_WHITELIST	Path to YAML whitelist for actuator actions (default config/act_whitelist.yml)
ACT_SANDBOX	Directory for actuator file writes (default sandbox)
ACT_TEMPLATES	Path to YAML templates for actuator (default config/act_templates.yml)
SMTP_HOST	SMTP server for email actions
SMTP_PORT	SMTP port (default 25)
SMTP_USER	SMTP username
SMTP_PASS	SMTP password
SMTP_FROM	Sender address for emails

Usage
Install dependencies
bash
Copy
Edit
pip install -r requirements.txt
Voice interaction
After installing dependencies, run

bash
Copy
Edit
python voice_loop.py
to start a continuous, full-duplex conversation using your microphone and speakers.

Full duplex: SentientOS listens while speaking so you can interrupt at any time.

Streaming replies: Speech output streams chunk by chunk and adapts to recent emotional context.

Persona adaptation: Persona and speaking style adapt automatically based on detected emotion trends.

Multimodal fusion: Emotion detection combines audio tone, text sentiment, and (optionally) vision input, logging each source’s weight.

Browser demo: Use browser_voice.py for a simple demo that lets you switch personas in real time, upload audio for emotion analysis, and view live emotion fusion.

Memory management
memory_manager.py provides persistent storage of message fragments. Each fragment includes a 64‑dimensional emotion vector and is indexed for simple vector search.

Optional helpers:

purge_memory(max_age_days=None, max_files=None) removes old fragments by age or keeps the newest max_files records.

summarize_memory() concatenates raw fragments into daily summary files under logs/memory/distilled.

User profile and prompt assembly
The user_profile module stores persistent key-value data about the user in profile.json inside MEMORY_DIR.
prompt_assembler combines this profile information with relevant memory snippets (retrieved via memory_manager.get_context) to build a rich prompt for the models.

Command-line usage via memory_cli.py
bash
Copy
Edit
python memory_cli.py purge --age 30       # delete fragments older than 30 days
python memory_cli.py purge --max 1000     # keep only the most recent 1000 fragments
python memory_cli.py summarize            # build/update daily summaries
python memory_cli.py playback --last 5    # show recent fragments with emotion labels and sources
python memory_cli.py timeline             # view the emotion timeline/mood trend
python memory_cli.py actions --last 5     # show recent actuator events
python memory_cli.py actions --last 5 --reflect  # include reflections
These commands can be invoked manually or scheduled via cron/Task Scheduler.

Actuator CLI
```bash
python api/actuator.py shell "ls -l"
python api/actuator.py http --url https://example.com
python api/actuator.py write --file out.txt --text "hello"
python api/actuator.py email --to user@example.com --subject hi --body "hello"
python api/actuator.py webhook --url http://hook --payload '{"ping":1}'
python api/actuator.py template --name greet --params '{"name":"Ada"}'
python api/actuator.py logs --last 5
python api/actuator.py templates           # list template names
python api/actuator.py hello --name Bob    # example plugin actuator
python api/actuator.py template_help --name greet  # show parameter help
python api/actuator.py shell "ls" --dry    # simulate without side effects
```

The `/act` endpoint can run actions asynchronously when `{"async": true}` is
sent. Poll `/act/status/<id>` or connect to `/act/stream/<id>` for live status
updates.

Log tailing
Use memory_tail.py to stream new entries from logs/memory.jsonl:

bash
Copy
Edit
python memory_tail.py
Pass --file to tail a different log.

Run tests
bash
Copy
Edit
pytest
No secrets are present in this repo.
Copy .env.example to .env and fill in your credentials before running.