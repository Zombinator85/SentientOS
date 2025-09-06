from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import socket
import struct
import time
import threading
from pathlib import Path
from queue import Queue
from typing import Dict, Tuple

POLL_INTERVAL = 5


def _get_gateways() -> Dict[str, str]:
    gateways: Dict[str, str] = {}
    try:
        with open("/proc/net/route", "r", encoding="utf-8") as fh:
            lines = fh.readlines()[1:]
        for line in lines:
            parts = line.strip().split()
            if len(parts) < 3 or parts[1] != "00000000":
                continue
            iface = parts[0]
            gateway_hex = parts[2]
            try:
                gw = socket.inet_ntoa(struct.pack("<L", int(gateway_hex, 16)))
            except Exception:
                gw = "0.0.0.0"
            gateways[iface] = gw
    except Exception:
        pass
    return gateways


def _get_net_info() -> Tuple[Dict[str, Dict], Dict[str, object], Dict[int, str]]:
    interfaces: Dict[str, Dict] = {}
    counters: Dict[str, object] = {}
    open_ports: Dict[int, str] = {}
    try:
        import psutil

        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, st in stats.items():
            if not st.isup:
                continue
            ips = [a.address for a in addrs.get(name, []) if a.family == socket.AF_INET]
            interfaces[name] = {"ips": ips, "speed": st.speed}
        counters = psutil.net_io_counters(pernic=True)
        for c in psutil.net_connections(kind="inet"):
            if c.status != psutil.CONN_LISTEN:
                continue
            port = c.laddr.port
            proc = "unknown"
            if c.pid:
                try:
                    proc = psutil.Process(c.pid).name()
                except Exception:
                    pass
            open_ports[port] = proc
    except Exception:
        pass
    gateways = _get_gateways()
    for iface, gw in gateways.items():
        if iface in interfaces:
            interfaces[iface]["gateway"] = gw
    return interfaces, counters, open_ports


def _block_port(port: int) -> None:
    """Placeholder for blocking a port."""
    return None


def _write_policy_flag(path: Path, restriction: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(restriction, encoding="utf-8")
    except Exception:
        pass


def _enqueue_resync(directory: Path) -> None:
    msg = {"event": "network_resync", "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fname = directory / f"{int(time.time()*1000)}_network.json"
        fname.write_text(json.dumps(msg), encoding="utf-8")
    except Exception:
        pass


def _ping(ip: str, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, 80), timeout=timeout):
            return True
    except OSError:
        return False


def run_loop(
    stop: threading.Event,
    ledger_queue: Queue,
    config: dict,
    poll_interval: int = POLL_INTERVAL,
    pulse_dir: Path = Path("/pulse"),
    fed_dir: Path = Path("/glow/federation_queue"),
) -> None:
    policies = config.get("network_policies", {})
    allow_ports = set(policies.get("allow_ports", []))
    block_ports = set(policies.get("block_ports", []))
    max_band = float(policies.get("max_bandwidth_percent", 90))
    mode = str(policies.get("mode", "monitor_only"))
    enforce = mode != "monitor_only"
    policy_flag = pulse_dir / "network_policy"

    interfaces, prev_counters, open_ports = _get_net_info()
    seen_ports = set(open_ports.keys()) | allow_ports | block_ports
    if not interfaces:
        ledger_queue.put({"event": "network_daemon_init", "status": "no_interface"})

    while not stop.is_set():
        interfaces, counters, open_ports = _get_net_info()
        bandwidth: Dict[str, Dict[str, float]] = {}
        for iface, info in interfaces.items():
            sent = recv = percent = 0.0
            counter = counters.get(iface)
            prev = prev_counters.get(iface) if prev_counters else None
            speed = info.get("speed", 0)
            if counter and prev:
                sent = float(counter.bytes_sent - prev.bytes_sent)
                recv = float(counter.bytes_recv - prev.bytes_recv)
                capacity = speed * 125000  # Bytes/sec
                if capacity:
                    percent = ((sent + recv) / max(poll_interval, 1)) / capacity * 100
                    if percent > max_band:
                        ledger_queue.put(
                            {
                                "event": "net_saturation",
                                "interface": iface,
                                "usage_percent": percent,
                            }
                        )
            bandwidth[iface] = {"sent": sent, "recv": recv, "percent": percent}
        prev_counters = counters

        for port, proc in open_ports.items():
            if port not in seen_ports and port not in allow_ports and port not in block_ports:
                ledger_queue.put(
                    {
                        "event": "net_port_unexpected",
                        "port": port,
                        "process": proc,
                    }
                )
                seen_ports.add(port)
            if port in block_ports and enforce:
                _block_port(port)
                _write_policy_flag(policy_flag, f"blocked:{port}")
                ledger_queue.put({"event": "net_blocked", "port": port})

        ledger_queue.put(
            {
                "event": "network_state",
                "level": "DEBUG",
                "interfaces": interfaces,
                "bandwidth": bandwidth,
                "open_ports": list(open_ports.keys()),
            }
        )

        peer = config.get("federation_peer_ip")
        if peer and not _ping(str(peer)):
            ledger_queue.put({"event": "federation_link_down", "peer": peer})
            _enqueue_resync(fed_dir)

        if stop.wait(poll_interval):
            break
