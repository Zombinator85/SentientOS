@echo off
cd /d C:\SentientOS\api

REM ---- Kill existing processes to prevent race conditions ----
echo Killing any existing bridge, relay, or Ollama processes...
taskkill /IM "python.exe" /F >nul 2>&1
taskkill /IM "ollama.exe" /F >nul 2>&1

REM ---- Launch ngrok MAIN (gpt4o, mixtral, relay) ----
start "NGROK MAIN" cmd /k ngrok start --all --config ngrok_main.yml

REM ---- Launch ngrok ALT (deepseek, ds-relay, dashboard) ----
start "NGROK ALT" cmd /k ngrok start --all --config ngrok_alt.yml

REM ---- Start Ollama Serve ----
timeout /t 3 >nul
start "OLLAMA" cmd /k ollama serve

REM ---- Wait a moment for Ollama to boot ----
timeout /t 3 >nul

REM ---- Start all three Telegram bridges ----
start "GPT4O" cmd /k waitress-serve --host=0.0.0.0 --port=9977 lumos_telegram_gpt4o_bridge:app
start "MIXTRAL" cmd /k waitress-serve --host=0.0.0.0 --port=9988 lumos_telegram_mixtral_bridge:app
start "DEEPSEEK" cmd /k waitress-serve --host=0.0.0.0 --port=9966 lumos_telegram_third_bridge:app

REM ---- Start the relay ----
start "RELAY" cmd /k python sentientos_relay.py

REM ---- Wait for all servers to come up ----
timeout /t 8 >nul

REM ---- Bind webhooks to the current ngrok URLs ----
start "BIND WEBHOOKS" cmd /k python bind_tunnels_dual_fixed.py

REM ---- (Optional) Show a console "DONE" window ----
start "READY" cmd /k echo All bridges, relay, and ngrok tunnels are launched. Monitor each window!

REM ---- Exit the launcher (optional) ----
exit
