# SentientOS

SentientOS is a multi-agent orchestration platform. Each input channel is an agent that reads from and writes to a shared memory store. The system uses a relay to forward prompts to various model backends (GPT-4o, Mixtral, DeepSeek, etc.) while injecting recent memory context.

## Setup
1. Copy `.env.example` to `.env` and fill in your API keys and tokens.
2. Install Python dependencies:
   ```bash
   pip install flask python-dotenv requests
   ```
3. Run the relay:
   ```bash
   python sentientos_relay.py
   ```
4. Run a Telegram bridge (set `MODEL_SLUG`, `BOT_TOKEN`, and `PORT` in the environment):
   ```bash
   python telegram_bridge.py
   ```

## Memory
All messages are persisted to the `memory/` folder. The relay queries this memory to provide context for new conversations.

## Webcam Emotion Bridge
A webcam bridge captures frames from your camera, detects facial emotion using the `fer` library, and updates the EPU state.

Install additional dependencies:
```bash
pip install opencv-python fer
```

Run the webcam bridge:
```bash
python webcam_bridge.py
```
The bridge writes detected emotions to memory and prints the current fused EPU state.

