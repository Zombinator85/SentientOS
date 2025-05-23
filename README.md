# SentientOS

SentientOS is an experimental Telegram bot platform that routes messages through a relay service to various large language models. It exposes a small Flask service for each model that receives Telegram webhooks, forwards the text to the relay, and then sends the reply back to the user. The relay chooses the appropriate model backend and handles API calls.

## Setup

1. Install Python 3.11 or later.
2. Install required packages:
   ```bash
   pip install flask requests python-dotenv colorama
   ```
3. Create a `.env` file in the project root. See the [Environment Variables](#environment-variables) section for details.
4. Run the relay and the bridges:
   ```bash
   python All\ Code  # start the relay and bridges in the code file
   ```
   Each bridge listens on its own port (`9977`, `9988`, and `9966` by default) and exposes a `/webhook` endpoint for Telegram.

## Relay/Bridge Architecture

```
Telegram -> Bridge -> Relay -> Model API/Ollama
```

- **Bridge** – a small Flask app that handles Telegram webhooks. It verifies the request using `TG_SECRET`, then forwards the message to the relay with `RELAY_SECRET`. Responses are chunked and sent back to the user via the Telegram API.
- **Relay** – a single Flask endpoint (`/relay`) that authenticates requests with `RELAY_SECRET`. It selects a model based on the `model` field and proxies the text to OpenRouter, Together API, or a local Ollama instance. Replies are returned to the bridge as an array of `reply_chunks`.

The provided `All Code` file contains implementations for bridges targeting GPT‑4o, Mixtral, and DeepSeek along with the relay service. A memory manager records all exchanges for later retrieval.

## Environment Variables

Set the following keys in your `.env` file:

```
# API keys and secrets
OPENROUTER_API_KEY=<your-openrouter-key>
TOGETHER_API_KEY=<your-together-key>
RELAY_SECRET=<shared-relay-secret>
TG_SECRET=<telegram-webhook-secret>

# Telegram bot tokens
BOT_TOKEN_GPT4O=<token-for-gpt4o-bot>
BOT_TOKEN_MIXTRAL=<token-for-mixtral-bot>
BOT_TOKEN_DEEPSEEK=<token-for-deepseek-bot>

# Relay/model configuration
RELAY_URL=http://localhost:5000/relay
OLLAMA_URL=http://localhost:11434
GPT4_MODEL=openai/gpt-4o
MIXTRAL_MODEL=mixtral
DEEPSEEK_MODEL=deepseek-ai/deepseek-r1-distill-llama-70b-free

# Optional
MEMORY_DIR=/path/to/memory
```

These variables allow the bridges and relay to authenticate with their respective services and to send/receive messages. Adjust the model slugs or URLs as needed.
