"""Avatar-side heartbeat monitor."""
import socket
import time

PORT = int(os.getenv("HEARTBEAT_PORT", "9001"))
TIMEOUT = 10


def run() -> None:  # pragma: no cover - realtime loop
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(TIMEOUT)
    last = time.time()
    while True:
        try:
            data, _ = sock.recvfrom(1024)
            if b"ping" in data:
                last = time.time()
        except socket.timeout:
            pass
        if time.time() - last > TIMEOUT:
            print("Heartbeat missing")
            last = time.time()


if __name__ == "__main__":
    run()
