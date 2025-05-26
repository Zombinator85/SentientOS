import subprocess
from pathlib import Path

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - fallback when requests isn't installed
    requests = None

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - fallback when PyYAML isn't installed
    yaml = None
import ast

# Load whitelist
WHITELIST_PATH = Path("config/act_whitelist.yml")
def _load_yaml(text: str):
    if yaml:
        return yaml.safe_load(text)
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        key = key.strip()
        val = val.strip()
        if val.startswith('[') and val.endswith(']'):
            data[key] = ast.literal_eval(val)
        else:
            try:
                data[key] = int(val)
            except ValueError:
                data[key] = val
    return data

if WHITELIST_PATH.exists():
    WHITELIST = _load_yaml(WHITELIST_PATH.read_text()) or {}
else:
    WHITELIST = {"shell": [], "http": [], "timeout": 30}

SANDBOX_DIR = Path("sandbox")
SANDBOX_DIR.mkdir(exist_ok=True)

def _allowed_shell(cmd: str) -> bool:
    first = cmd.strip().split()[0] if cmd.strip() else ""
    return first in WHITELIST.get("shell", [])

def run_shell(cmd: str, cwd: str = ".") -> dict:
    if not _allowed_shell(cmd):
        raise PermissionError("Command not allowed")
    res = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=WHITELIST.get("timeout", 30),
    )
    return {
        "code": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }

def http_fetch(url: str, method: str = "GET", **kwargs) -> dict:
    allowed = any(url.startswith(p) for p in WHITELIST.get("http", []))
    if not allowed:
        raise PermissionError("URL not allowed")
    timeout = WHITELIST.get("timeout", 30)
    if requests:
        resp = requests.request(method, url, timeout=timeout, **kwargs)
        return {"status": resp.status_code, "text": resp.text}
    import urllib.request
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode()
        status = r.getcode()
    return {"status": status, "text": text}

def file_write(path: str, content: str) -> dict:
    target = SANDBOX_DIR / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"written": str(target)}

def dispatch(intent: dict) -> dict:
    itype = intent.get("type")
    if itype == "shell":
        return run_shell(intent.get("cmd", ""), cwd=intent.get("cwd", "."))
    if itype == "http":
        url = intent.get("url", "")
        method = intent.get("method", "GET")
        extras = {k: v for k, v in intent.items() if k not in {"type", "url", "method"}}
        return http_fetch(url, method=method, **extras)
    if itype == "file":
        return file_write(intent.get("path", ""), intent.get("content", ""))
    raise ValueError("Unsupported intent")
