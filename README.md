# SentientOS Scripts

This repository contains a collection of small utilities for running the SentientOS bridges and tools. The original project bundled all code into a single file. Each script has now been extracted into its own file for clarity.

## Telegram Bridges
- `lumos_telegram_gpt4o_bridge.py` – Telegram webhook bridge for the GPT‑4o model.
- `lumos_telegram_mixtral_bridge.py` – Bridge for the Mixtral model.
- `lumos_telegram_third_bridge.py` – Bridge for the DeepSeek model.

## Utilities
- `bind_tunnels_dual_fixed.py` – Rebinds Telegram webhooks using ngrok tunnels.
- `launch_bridges.bat` – Windows batch script to launch ngrok, bridges and the relay.
- `sentientos_relay.py` – Relay service that forwards messages to the appropriate model.
- `memory_tail.py` – Tails the memory log with colored output.
- `memory_manager.py` – Simple persistent memory store used by the other tools.

## Heartbeat Scripts
- `gpt4o_heartbeat.py`, `mixtral_heartbeat.py`, `deepseek_heartbeat.py` – Periodic heartbeat clients for each model.
- `cathedral_heartbeat.py` – Combined heartbeat that cycles through multiple agents.

## Configuration
- `ngrok_main.yml` and `ngrok_alt.yml` – Example ngrok configurations.
- `.env.example` – Example environment file showing required variables.

The original `All Code` file is kept for reference but each component now lives in its own file.
