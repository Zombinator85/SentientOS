import subprocess
import time
import os


def kill_processes():
    """Kill leftover python and ollama processes."""
    for proc in ("python.exe", "ollama.exe"):
        try:
            subprocess.run(["taskkill", "/IM", proc, "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            # taskkill is Windows-only; ignore if not present
            pass


def start_process(name, command):
    """Start a subprocess in a new window if possible."""
    if os.name == 'nt':
        # Windows: start in new cmd window
        subprocess.Popen(["start", name, "cmd", "/k"] + command, shell=True)
    else:
        # Non-Windows: run command directly
        subprocess.Popen(command)


def main():
    os.chdir(r"C:\SentientOS\api") if os.name == 'nt' else None
    print("Killing any existing bridge, relay, or Ollama processes...")
    kill_processes()

    start_process("NGROK MAIN", ["ngrok", "start", "--all", "--config", "ngrok_main.yml"])
    start_process("NGROK ALT", ["ngrok", "start", "--all", "--config", "ngrok_alt.yml"])

    time.sleep(3)
    start_process("OLLAMA", ["ollama", "serve"])
    time.sleep(3)

    start_process("GPT4O", ["waitress-serve", "--host=0.0.0.0", "--port=9977", "lumos_telegram_gpt4o_bridge:app"])
    start_process("MIXTRAL", ["waitress-serve", "--host=0.0.0.0", "--port=9988", "lumos_telegram_mixtral_bridge:app"])
    start_process("DEEPSEEK", ["waitress-serve", "--host=0.0.0.0", "--port=9966", "lumos_telegram_third_bridge:app"])

    start_process("RELAY", ["python", "sentientos_relay.py"])
    time.sleep(8)

    start_process("BIND WEBHOOKS", ["python", "bind_tunnels_dual_fixed.py"])

    print("All bridges, relay, and ngrok tunnels are launched. Monitor each window!")


if __name__ == "__main__":
    main()
