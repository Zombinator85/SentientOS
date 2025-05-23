# SentientOS

SentientOS is a multi-agent orchestration platform. Each input channel is an agent that reads from and writes to a shared memory store. The system uses a relay to forward prompts to various model backends (GPT-4o, Mixtral, DeepSeek, etc.) while injecting recent memory context.

## Setup
1. Copy `.env.example` to `.env` and fill in your API keys and tokens.
2. Install Python dependencies:
   ```bash
   pip install flask python-dotenv requests speechrecognition
   ```
3. Run the relay:
   ```bash
   python sentientos_relay.py
   ```
4. Run a Telegram bridge (set `MODEL_SLUG`, `BOT_TOKEN`, and `PORT` in the environment):
   ```bash
   python telegram_bridge.py
   ```
5. Optionally run the microphone bridge for voice input and emotion detection:
   ```bash
   python microphone_bridge.py
   ```

## Memory
All messages are persisted to the `memory/` folder. The relay queries this memory to provide context for new conversations. When using the microphone bridge, each fragment also records a detected `emotion` label so agents can respond empathetically.
