"""Avatar-side heartbeat monitor."""
from logging_config import get_log_path
import socket
import time
import subprocess
from pathlib import Path

LOG_FILE = get_log_path("avatar_restarts.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
CMD = os.getenv("AVATAR_RECEIVER_CMD")
process = None

PORT = int(os.getenv("HEARTBEAT_PORT", "9001"))
TIMEOUT = 10


def run() -> None:  # pragma: no cover - realtime loop
    global process
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(TIMEOUT)
    last = time.time()
    if CMD:
        process = subprocess.Popen(CMD.split())
    while True:
        try:
            data, _ = sock.recvfrom(1024)
            if b"ping" in data:
                last = time.time()
        except socket.timeout:
            pass
        if time.time() - last > TIMEOUT:
            print("Heartbeat missing")
            if CMD:
                if process and process.poll() is None:
                    process.kill()
                process = subprocess.Popen(CMD.split())
                with LOG_FILE.open("a", encoding="utf-8") as f:
                    f.write(f"{time.time()} restart\n")
            last = time.time()


if __name__ == "__main__":
    run()
