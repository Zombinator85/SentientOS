from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

import os
import json
import re
import stat
import subprocess
import smtplib
import socket
import ssl
import http.client
import threading
import time
import queue
import shlex
from email.message import EmailMessage
from pathlib import Path
import ast
import ipaddress
from dataclasses import dataclass
from typing import Any, Dict, Callable, Mapping, Sequence, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

from logging_config import resolve_log_path
from sentientos.optional_deps import optional_import

# --- Pluggable actuator registry -------------------------------------------

class BaseActuator:
    """Interface for pluggable actuator types."""

    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


ACTUATORS: dict[str, BaseActuator] = {}

AUTONOMOUS_LOG = resolve_log_path("autonomous_calls.jsonl", "AUTONOMOUS_CALLS_LOG")


def _authorize_effect() -> None:
    """Apply Cathedral privilege policy immediately before a protected effect."""
    require_admin_banner()
    require_lumos_approval()


def register_actuator(name: str, actuator: BaseActuator) -> None:
    ACTUATORS[name] = actuator


# Load whitelist
WHITELIST_PATH = Path(os.getenv("ACT_WHITELIST", "config/act_whitelist.yml"))
TEMPLATES_PATH = Path(os.getenv("ACT_TEMPLATES", "config/act_templates.yml"))
def _load_yaml(text: str) -> dict[str, object]:
    yaml = optional_import("pyyaml", feature="actuator_whitelist")
    if yaml:
        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    data: dict[str, object] = {}
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

SANDBOX_DIR = Path(os.getenv("ACT_SANDBOX", "sandbox"))


class ShellActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        argv, legacy_cmd = _canonical_shell_argv(intent)
        result = run_shell(argv, cwd=intent.get("cwd", "."))
        result["argv"] = list(argv)
        if legacy_cmd is not None:
            result["legacy_cmd"] = legacy_cmd
        return result


class HttpActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        unknown = set(intent) - {"type", "url", "method", "headers", "body", "json"}
        if unknown:
            raise ValueError(f"unsupported HTTP intent fields: {', '.join(sorted(unknown))}")
        return http_fetch(
            intent.get("url", ""), method=intent.get("method", "GET"),
            headers=intent.get("headers"), body=intent.get("body"), json_data=intent.get("json"),
        )


class FileActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        return file_write(intent.get("path", ""), intent.get("content", ""))


class EmailActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        return send_email(intent.get("to", ""), intent.get("subject", ""), intent.get("body", ""))


class WebhookActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        return trigger_webhook(intent.get("url", ""), intent.get("payload", {}))


class WorkflowActuator(BaseActuator):
    """Execute a registered workflow via ``workflow_controller``."""

    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        _authorize_effect()
        name = intent.get("name")
        if not name:
            raise ValueError("workflow name required")
        import workflow_controller as wc

        ok = wc.run_workflow(name)
        return {"ok": ok}


class TalkbackActuator(BaseActuator):
    """Send synthesized speech through a configured camera audio channel."""

    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        _authorize_effect()
        message = intent.get("message") or intent.get("text")
        if not message or not isinstance(message, str):
            raise ValueError("talkback requires a 'message' string")
        url = intent.get("url") or intent.get("rtsp") or None
        ffmpeg_path = intent.get("ffmpeg")
        voice = intent.get("voice")
        from talkback_bridge import CameraTalkback
        talkback = CameraTalkback(rtsp_url=url, ffmpeg_path=ffmpeg_path)
        audio_path = talkback.speak(message, voice=voice)
        return {"ok": True, "target": talkback.rtsp_url, "audio_path": str(audio_path)}


BUILTIN_ACTUATOR_TYPES: Mapping[str, type[BaseActuator]] = {
    "shell": ShellActuator,
    "http": HttpActuator,
    "file": FileActuator,
    "email": EmailActuator,
    "webhook": WebhookActuator,
    "workflow": WorkflowActuator,
    "talkback": TalkbackActuator,
}


def register_builtin_actuators() -> None:
    for name, actuator_type in BUILTIN_ACTUATOR_TYPES.items():
        if name not in ACTUATORS:
            register_actuator(name, actuator_type())


def initialize_actuators(*, load_external_plugins: bool = False) -> None:
    """Idempotently register built-ins; reject retired filesystem plugins."""
    if load_external_plugins:
        raise RuntimeError("external actuator plugins are disabled")
    register_builtin_actuators()


initialize_actuators()


def _match_patterns(value: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if pat.startswith('^'):
            if re.match(pat, value):
                return True
        else:
            import fnmatch
            if '*' in pat or '?' in pat:
                if fnmatch.fnmatch(value, pat):
                    return True
            else:
                if value.startswith(pat):
                    return True
    return False


_HTTP_DEFAULT_PORTS = {"http": 80, "https": 443}
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def _canonical_hostname(hostname: str) -> str:
    """Return an exact, comparison-safe IP literal or DNS hostname."""
    candidate = hostname.rstrip(".")
    if not candidate:
        raise ValueError("missing URL host")
    try:
        return ipaddress.ip_address(candidate).compressed.lower()
    except ValueError:
        try:
            canonical = candidate.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("malformed URL host") from exc
        labels = canonical.split(".")
        if any(not label or len(label) > 63 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) for label in labels):
            raise ValueError("malformed URL host")
        return canonical


def _canonical_http_url(value: object, *, policy_entry: bool = False) -> tuple[str, str, int, str]:
    """Validate an HTTP URL and return URL, scheme, effective port, and path."""
    if not isinstance(value, str):
        raise ValueError("malformed URL: string required")
    if _CONTROL_CHARACTERS.search(value):
        raise ValueError("malformed URL: control character rejected")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("malformed URL") from exc
    scheme = parsed.scheme.lower()
    if scheme not in _HTTP_DEFAULT_PORTS:
        raise ValueError("unsupported URL scheme")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL userinfo rejected")
    if parsed.hostname is None:
        raise ValueError("missing URL host")
    try:
        port = parsed.port or _HTTP_DEFAULT_PORTS[scheme]
    except ValueError as exc:
        raise ValueError("malformed URL port") from exc
    host = _canonical_hostname(parsed.hostname)
    path = parsed.path or "/"
    if policy_entry and (parsed.query or parsed.fragment):
        raise ValueError("malformed URL policy entry")
    if policy_entry and path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    bracketed_host = f"[{host}]" if ":" in host else host
    default_port = _HTTP_DEFAULT_PORTS[scheme]
    netloc = bracketed_host if port == default_port else f"{bracketed_host}:{port}"
    canonical = urlunsplit(SplitResult(scheme, netloc, path, parsed.query, ""))
    return canonical, host, port, path


def _authorized_http_url(value: object) -> str:
    """Authorize a canonical URL against exact origins and path-component scopes."""
    canonical, host, port, path = _canonical_http_url(value)
    entries = WHITELIST.get("http", [])
    if not isinstance(entries, list):
        raise PermissionError("HTTP destination policy is malformed")
    for entry in entries:
        try:
            _policy_url, policy_host, policy_port, policy_path = _canonical_http_url(entry, policy_entry=True)
            policy_scheme = urlsplit(_policy_url).scheme
        except ValueError:
            continue
        if policy_scheme != urlsplit(canonical).scheme or policy_host != host or policy_port != port:
            continue
        if policy_path == "/" or path == policy_path or path.startswith(policy_path + "/"):
            return canonical
    raise PermissionError("HTTP destination not allowed")


def _canonical_smtp_endpoint(host: object, port: object) -> tuple[str, int]:
    if not isinstance(host, str) or _CONTROL_CHARACTERS.search(host):
        raise ValueError("malformed SMTP endpoint")
    if not isinstance(port, (str, int)) or isinstance(port, bool):
        raise ValueError("malformed SMTP endpoint")
    try:
        port_number = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("malformed SMTP endpoint") from exc
    if not 1 <= port_number <= 65535:
        raise ValueError("malformed SMTP endpoint")
    raw_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    return _canonical_hostname(raw_host), port_number


def _authorized_smtp_endpoint(host: object, port: object) -> tuple[str, int]:
    endpoint = _canonical_smtp_endpoint(host, port)
    entries = WHITELIST.get("smtp", [])
    if not isinstance(entries, list):
        raise PermissionError("SMTP endpoint policy is malformed")
    for entry in entries:
        if not isinstance(entry, str):
            continue
        try:
            if entry.startswith("["):
                end = entry.find("]")
                if end < 0 or entry[end + 1 : end + 2] != ":":
                    continue
                candidate = _canonical_smtp_endpoint(entry[: end + 1], entry[end + 2 :])
            else:
                candidate_host, separator, candidate_port = entry.rpartition(":")
                if not separator:
                    continue
                candidate = _canonical_smtp_endpoint(candidate_host, candidate_port)
        except ValueError:
            continue
        if candidate == endpoint:
            return endpoint
    raise PermissionError("SMTP endpoint not allowed")


def _canonical_mailbox(value: object, *, field: str = "recipient") -> tuple[str, str]:
    if not isinstance(value, str) or _CONTROL_CHARACTERS.search(value):
        raise ValueError(f"malformed {field}")
    if value.count("@") != 1:
        raise ValueError(f"malformed {field}")
    local, domain = value.split("@")
    if not local or len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local):
        raise ValueError(f"malformed {field}")
    return local, _canonical_hostname(domain)


def _authorized_recipient(value: object) -> str:
    local, domain = _canonical_mailbox(value)
    entries = WHITELIST.get("email", [])
    if not isinstance(entries, list):
        raise PermissionError("email recipient policy is malformed")
    for entry in entries:
        if not isinstance(entry, str):
            continue
        if entry.startswith("*@"):
            try:
                if _canonical_hostname(entry[2:]) == domain:
                    return f"{local}@{domain}"
            except ValueError:
                continue
        else:
            try:
                allowed_local, allowed_domain = _canonical_mailbox(entry)
            except ValueError:
                continue
            if allowed_local == local and allowed_domain == domain:
                return f"{local}@{domain}"
    raise PermissionError("email recipient not allowed")


MAX_ARGV_COUNT = 128
MAX_ARGUMENT_BYTES = 4096
MAX_ARGV_BYTES = 32768
_LEGACY_SHELL_GRAMMAR = re.compile(r"(?:\r|\n|;|&&|\|\||\||[<>]|`|\$\(|[<>]\(|&)")


def _validate_argv(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        raise ValueError("malformed command: argv must be a sequence of strings")
    if not value:
        raise ValueError("missing command: argv must be nonempty")
    if len(value) > MAX_ARGV_COUNT:
        raise ValueError("argument budget exceeded: too many arguments")
    argv: list[str] = []
    total = 0
    for item in value:
        if not isinstance(item, str):
            raise ValueError("invalid argument: argv entries must be strings")
        if "\x00" in item:
            raise ValueError("invalid argument: NUL is forbidden")
        size = len(item.encode("utf-8"))
        if size > MAX_ARGUMENT_BYTES:
            raise ValueError("argument budget exceeded: argument too long")
        total += size
        argv.append(item)
    if not argv[0]:
        raise ValueError("missing command: argv[0] must be nonempty")
    if total > MAX_ARGV_BYTES:
        raise ValueError("argument budget exceeded: argv too large")
    return tuple(argv)


def _legacy_cmd_argv(cmd: object) -> tuple[str, ...]:
    if not isinstance(cmd, str) or not cmd.strip():
        raise ValueError("missing command: provide argv")
    if _LEGACY_SHELL_GRAMMAR.search(cmd):
        raise ValueError("rejected shell grammar: provide explicit argv")
    try:
        # Compatibility is parsing only.  The supplied text is never executed.
        parsed = shlex.split(cmd, posix=True)
    except ValueError as exc:
        raise ValueError("malformed command: ambiguous legacy cmd") from exc
    return _validate_argv(parsed)


def _canonical_shell_argv(intent: Mapping[str, object]) -> tuple[tuple[str, ...], str | None]:
    if "argv" in intent:
        return _validate_argv(intent["argv"]), None
    cmd = intent.get("cmd")
    return _legacy_cmd_argv(cmd), cmd if isinstance(cmd, str) else None


def _canonical_policy_executable(value: object) -> str:
    """Return the process-real executable named by a structured shell rule."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PermissionError("shell command policy is malformed: invalid executable")
    supplied = Path(value)
    if not supplied.is_absolute():
        raise PermissionError("shell command policy is malformed: executable must be an explicit path")
    try:
        executable = supplied.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PermissionError("shell command policy is malformed: executable does not exist") from exc
    if not executable.is_file():
        raise PermissionError("shell command policy is malformed: executable is not a regular file")
    if os.name == "posix" and not os.access(executable, os.X_OK):
        raise PermissionError("shell command policy is malformed: executable is not executable")
    return str(executable)


def _authorized_shell_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Bind an exact alias/executable and the complete argv to one command rule."""
    rules = WHITELIST.get("shell", [])
    if not isinstance(rules, list):
        raise PermissionError("shell command policy is malformed: shell must be a list")
    requested = argv[0]
    matches: list[tuple[str, Sequence[object]]] = []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"alias", "executable", "arguments"}:
            raise PermissionError("shell command policy is malformed: structured rule required")
        alias = rule["alias"]
        arguments = rule["arguments"]
        if (
            not isinstance(alias, str)
            or not alias
            or "\x00" in alias
            or not isinstance(arguments, list)
        ):
            raise PermissionError("shell command policy is malformed: invalid rule")
        executable = _canonical_policy_executable(rule["executable"])
        if requested == alias or requested == executable:
            matches.append((executable, arguments))
    if len(matches) != 1:
        raise PermissionError("shell command not allowed")

    executable, slots = matches[0]
    supplied_arguments = argv[1:]
    if len(supplied_arguments) != len(slots):
        raise PermissionError("shell command arguments not allowed: arity mismatch")
    admitted: list[str] = []
    for supplied, slot in zip(supplied_arguments, slots):
        if not isinstance(slot, dict) or not isinstance(slot.get("type"), str):
            raise PermissionError("shell command policy is malformed: invalid argument slot")
        slot_type = slot["type"]
        if slot_type == "literal" and set(slot) == {"type", "value"}:
            value = slot["value"]
            if not isinstance(value, str):
                raise PermissionError("shell command policy is malformed: invalid literal")
            if supplied != value:
                raise PermissionError("shell command arguments not allowed")
            admitted.append(supplied)
        elif slot_type == "one_of" and set(slot) == {"type", "values"}:
            values = slot["values"]
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) for value in values)
                or len(set(values)) != len(values)
            ):
                raise PermissionError("shell command policy is malformed: invalid one_of")
            if supplied not in values:
                raise PermissionError("shell command arguments not allowed")
            admitted.append(supplied)
        elif slot_type == "sandbox_path" and set(slot) == {"type"}:
            admitted.append(str(_safe_path(supplied, allow_empty=False)))
        else:
            raise PermissionError("shell command policy is malformed: unsupported argument slot")
    return (executable, *admitted)


def _timeout_seconds() -> float:
    timeout_value = WHITELIST.get("timeout", 30)
    if isinstance(timeout_value, (int, float)):
        return float(timeout_value)
    try:
        return float(str(timeout_value))
    except (TypeError, ValueError):
        return 30.0

def run_shell(argv: Sequence[str], cwd: str = ".") -> dict[str, object]:
    canonical_argv = _validate_argv(argv)
    authorized_argv = _authorized_shell_argv(canonical_argv)
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    cwd_path = _safe_path(cwd if cwd != "." else "")
    _authorize_effect()
    try:
        res = subprocess.run(
            authorized_argv,
            shell=False,
            capture_output=True,
            text=True,
            cwd=str(cwd_path),
            timeout=_timeout_seconds(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("execution timeout") from exc
    except OSError as exc:
        raise RuntimeError("execution failed") from exc
    return {
        "code": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }

MAX_RESOLVED_PEERS = 16
MAX_HTTP_BODY_BYTES = 1_048_576
MAX_HTTP_RESPONSE_BYTES = 1_048_576
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_RESERVED_HEADERS = frozenset({
    "host", "connection", "proxy-connection", "proxy-authorization",
    "transfer-encoding", "content-length", "upgrade", "te", "trailer",
})


@dataclass(frozen=True)
class _ResolvedPeer:
    family: int
    socktype: int
    proto: int
    sockaddr: tuple[object, ...]


def _resolved_endpoint_peers(host: str, port: int) -> tuple[_ResolvedPeer, ...]:
    """Take one bounded, validated resolution snapshot for an authorized endpoint."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        family = socket.AF_INET6 if literal.version == 6 else socket.AF_INET
        sockaddr: tuple[object, ...] = (literal.compressed, port, 0, 0) if literal.version == 6 else (literal.compressed, port)
        return (_ResolvedPeer(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, sockaddr),)

    try:
        answers = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    except OSError as exc:
        raise ConnectionError("endpoint resolution failed") from exc
    peers: list[_ResolvedPeer] = []
    seen: set[tuple[int, str, int, int]] = set()
    for answer in answers:
        if not isinstance(answer, tuple) or len(answer) != 5:
            raise ConnectionError("malformed endpoint resolution")
        family, socktype, proto, _canonname, sockaddr = answer
        if family not in (socket.AF_INET, socket.AF_INET6) or socktype != socket.SOCK_STREAM or proto not in (0, socket.IPPROTO_TCP):
            raise ConnectionError("malformed endpoint resolution")
        try:
            parts = tuple(sockaddr)
            if not isinstance(parts[0], (str, bytes, int, ipaddress.IPv4Address, ipaddress.IPv6Address)):
                raise ValueError
            address = ipaddress.ip_address(parts[0])
            if not isinstance(parts[1], int) or (family == socket.AF_INET6 and (len(parts) < 4 or not isinstance(parts[2], int) or not isinstance(parts[3], int))):
                raise ValueError
            answer_port = parts[1]
            flowinfo = cast(int, parts[2]) if family == socket.AF_INET6 else 0
            scope = cast(int, parts[3]) if family == socket.AF_INET6 else 0
        except (IndexError, TypeError, ValueError) as exc:
            raise ConnectionError("malformed endpoint resolution") from exc
        if address.version != (6 if family == socket.AF_INET6 else 4) or answer_port != port:
            raise ConnectionError("malformed endpoint resolution")
        if not address.is_global:
            raise PermissionError("DNS hostname resolved to a non-global address")
        key = (family, address.compressed, answer_port, scope)
        if key in seen:
            continue
        seen.add(key)
        canonical_sockaddr = ((address.compressed, port, flowinfo, scope) if family == socket.AF_INET6 else (address.compressed, port))
        peers.append(_ResolvedPeer(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, canonical_sockaddr))
        if len(peers) > MAX_RESOLVED_PEERS:
            raise ConnectionError("endpoint resolution candidate budget exceeded")
    if not peers:
        raise ConnectionError("endpoint resolution returned no peers")
    return tuple(peers)


def _connect_resolved_peer(peers: Sequence[_ResolvedPeer], timeout: float) -> socket.socket:
    last_error: OSError | None = None
    for peer in peers:
        sock = socket.socket(peer.family, peer.socktype, peer.proto)
        try:
            sock.settimeout(timeout)
            sock.connect(peer.sockaddr)
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
    raise ConnectionError("connection to resolved endpoint failed") from last_error


def _http_request_data(method: object, headers: object, body: object, json_data: object) -> tuple[str, dict[str, str], bytes | None]:
    if not isinstance(method, str) or not re.fullmatch(r"[A-Za-z]+", method):
        raise ValueError("malformed HTTP method")
    canonical_method = method.upper()
    if canonical_method not in _HTTP_METHODS:
        raise ValueError("unsupported HTTP method")
    if headers is None:
        admitted_headers: dict[str, str] = {}
    elif isinstance(headers, Mapping):
        admitted_headers = {}
        for name, value in headers.items():
            if not isinstance(name, str) or not isinstance(value, str) or not name or _CONTROL_CHARACTERS.search(name + value):
                raise ValueError("malformed HTTP header")
            if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) or name.lower() in _RESERVED_HEADERS:
                raise ValueError("reserved HTTP header rejected")
            admitted_headers[name] = value
    else:
        raise ValueError("HTTP headers must be a mapping")
    if body is not None and json_data is not None:
        raise ValueError("multiple HTTP body representations rejected")
    payload: bytes | None = None
    if body is not None:
        if isinstance(body, str):
            payload = body.encode("utf-8")
        elif isinstance(body, bytes):
            payload = body
        else:
            raise ValueError("HTTP body must be str or bytes")
    elif json_data is not None:
        try:
            payload = json.dumps(json_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("HTTP json body is not serializable") from exc
        if not any(name.lower() == "content-type" for name in admitted_headers):
            admitted_headers["Content-Type"] = "application/json"
    if payload is not None and len(payload) > MAX_HTTP_BODY_BYTES:
        raise ValueError("HTTP request body budget exceeded")
    return canonical_method, admitted_headers, payload


def _direct_http_transaction(canonical_url: str, method: str, headers: Mapping[str, str], body: bytes | None) -> dict[str, object]:
    parsed = urlsplit(canonical_url)
    assert parsed.hostname is not None
    host = _canonical_hostname(parsed.hostname)
    port = parsed.port or _HTTP_DEFAULT_PORTS[parsed.scheme]
    peers = _resolved_endpoint_peers(host, port)
    sock = _connect_resolved_peer(peers, _timeout_seconds())
    connection = http.client.HTTPConnection(host, port, timeout=_timeout_seconds())
    try:
        if parsed.scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
        connection.sock = sock
        request_headers = dict(headers)
        request_headers["Host"] = parsed.netloc
        connection.request(method, urlunsplit(("", "", parsed.path or "/", parsed.query, "")), body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
        if len(payload) > MAX_HTTP_RESPONSE_BYTES:
            raise RuntimeError("HTTP response body budget exceeded")
        charset = response.headers.get_content_charset() or "utf-8"
        return {"status": response.status, "text": payload.decode(charset, errors="replace")}
    finally:
        connection.close()


def http_fetch(url: object, method: object = "GET", *, headers: object = None, body: object = None, json_data: object = None) -> dict[str, object]:
    canonical_url = _authorized_http_url(url)
    canonical_method, canonical_headers, payload = _http_request_data(method, headers, body, json_data)
    _authorize_effect()
    return _direct_http_transaction(canonical_url, canonical_method, canonical_headers, payload)

def _safe_path(rel: object, *, allow_empty: bool = True) -> Path:
    """Resolve a caller-relative path beneath the sandbox custody boundary."""
    if not isinstance(rel, str):
        raise ValueError("sandbox path must be a string")
    if "\x00" in rel:
        raise ValueError("sandbox path must not contain NUL")
    if not rel and not allow_empty:
        raise ValueError("sandbox path must be nonempty")

    supplied = Path(rel)
    if supplied.is_absolute():
        raise PermissionError("Absolute sandbox paths are forbidden")

    sandbox_root = SANDBOX_DIR.resolve()
    target = (sandbox_root / supplied).resolve()
    try:
        target.relative_to(sandbox_root)
    except ValueError as exc:
        raise PermissionError("Path escapes sandbox") from exc
    return target


def _file_write_components(path: object) -> tuple[str, ...]:
    """Return a bounded lexical file path without consulting the filesystem."""
    if not isinstance(path, str):
        raise ValueError("sandbox path must be a string")
    if "\x00" in path:
        raise ValueError("sandbox path must not contain NUL")
    if not path:
        raise ValueError("sandbox path must be nonempty")
    supplied = Path(path)
    if supplied.is_absolute():
        raise PermissionError("Absolute sandbox paths are forbidden")
    components = tuple(component for component in supplied.parts if component not in ("", "."))
    if not components:
        raise ValueError("sandbox path must be nonempty")
    if ".." in components:
        raise PermissionError("Path escapes sandbox: parent traversal is forbidden")
    return components


def _descriptor_file_write_supported() -> bool:
    """Report whether the runtime can enforce the POSIX descriptor custody contract."""
    return (
        os.name == "posix"
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"))
    )


def _file_custody_checkpoint(event: str, directory_fd: int, component: str) -> None:
    """Test observation point; production traversal deliberately performs no action."""


def _open_directory_component(parent_fd: int, component: str, *, create: bool) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        return os.open(component, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(component, mode=0o755, dir_fd=parent_fd)
        except FileExistsError:
            pass
        try:
            return os.open(component, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise PermissionError(f"sandbox directory component rejected: {component}") from exc
    except OSError as exc:
        raise PermissionError(f"sandbox directory component rejected: {component}") from exc


def _open_sandbox_root() -> int:
    """Create and bind the configured sandbox root one no-follow component at a time."""
    configured = os.fspath(SANDBOX_DIR)
    root_path = Path(configured)
    components = tuple(part for part in root_path.parts if part not in (root_path.anchor, "", "."))
    if ".." in components:
        raise PermissionError("configured sandbox root parent traversal is forbidden")
    anchor = root_path.anchor or "."
    current_fd = os.open(
        anchor,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        for component in components:
            next_fd = _open_directory_component(current_fd, component, create=True)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def file_write(path: str, content: str) -> dict[str, object]:
    components = _file_write_components(path)
    if not isinstance(content, str):
        raise ValueError("file content must be a string")
    _authorize_effect()
    if not _descriptor_file_write_supported():
        raise RuntimeError("descriptor-relative no-follow file custody is unsupported on this platform")

    directory_fd = _open_sandbox_root()
    file_fd: int | None = None
    try:
        for component in components[:-1]:
            next_fd = _open_directory_component(directory_fd, component, create=True)
            os.close(directory_fd)
            directory_fd = next_fd
        leaf = components[-1]
        _file_custody_checkpoint("parent_bound", directory_fd, leaf)
        try:
            file_fd = os.open(
                leaf,
                os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o666,
                dir_fd=directory_fd,
            )
        except OSError as exc:
            raise PermissionError("sandbox file leaf rejected") from exc
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError("sandbox file leaf must be a regular file")
        if info.st_nlink > 1:
            raise PermissionError("sandbox file hardlink alias rejected")
        _file_custody_checkpoint("leaf_bound", directory_fd, leaf)
        os.ftruncate(file_fd, 0)
        payload = content.encode("utf-8")
        offset = 0
        while offset < len(payload):
            written = os.write(file_fd, payload[offset:])
            if written <= 0:
                raise OSError("descriptor write made no progress")
            offset += written
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(directory_fd)
    reporting_path = os.path.abspath(os.path.join(os.fspath(SANDBOX_DIR), *components))
    return {"written": reporting_path}


def send_email(to: str, subject: str, body: str) -> dict[str, object]:
    host = os.getenv("SMTP_HOST")
    if not host:
        raise EnvironmentError("SMTP not configured")
    canonical_host, port = _authorized_smtp_endpoint(host, os.getenv("SMTP_PORT", "25"))
    canonical_to = _authorized_recipient(to)
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    from_addr = os.getenv("SMTP_FROM", user or "noreply@example.com")
    canonical_from = "@".join(_canonical_mailbox(from_addr, field="sender"))
    if not isinstance(subject, str) or _CONTROL_CHARACTERS.search(subject):
        raise ValueError("email subject header injection rejected")
    msg = EmailMessage()
    msg["From"] = canonical_from
    msg["To"] = canonical_to
    msg["Subject"] = subject
    msg.set_content(body)
    _authorize_effect()
    peers = _resolved_endpoint_peers(canonical_host, port)
    smtp = smtplib.SMTP(timeout=_timeout_seconds())
    setattr(smtp, "_host", canonical_host)
    smtp.sock = _connect_resolved_peer(peers, _timeout_seconds())
    code, message = smtp.getreply()
    if code != 220:
        smtp.close()
        raise smtplib.SMTPConnectError(code, message)
    with smtp:
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)
    return {"sent": canonical_to}


def trigger_webhook(url: str, payload: Mapping[str, object]) -> dict[str, object]:
    response = http_fetch(url, method="POST", json_data=payload)
    return {"status": response["status"]}


TEMPLATES: dict[str, object] = {}
if TEMPLATES_PATH.exists():
    TEMPLATES = _load_yaml(TEMPLATES_PATH.read_text()) or {}


# --- Async handling ---------------------------------------------------------
TASK_QUEUE: "queue.Queue[tuple[str, Dict[str, Any], str | None, str | None]]" = queue.Queue()
ACTION_STATUS: dict[str, dict[str, object]] = {}
_worker_started = False


def _worker() -> None:
    while True:
        action_id, intent, explanation, user = TASK_QUEUE.get()
        ACTION_STATUS[action_id] = {"status": "running"}
        try:
            result = act(intent, explanation=explanation, user=user)
            ACTION_STATUS[action_id] = {"status": "finished", "result": result}
        except Exception as e:  # pragma: no cover - defensive
            ACTION_STATUS[action_id] = {"status": "failed", "error": str(e)}
        TASK_QUEUE.task_done()


def start_async(intent: Dict[str, Any], explanation: str | None = None, user: str | None = None) -> str:
    """Queue an action for background execution and return its id."""
    global _worker_started
    _authorize_effect()
    action_id = f"a{int(time.time()*1000)}"
    ACTION_STATUS[action_id] = {"status": "queued"}
    queued_intent = _normalize_intent(intent)
    TASK_QUEUE.put((action_id, queued_intent, explanation, user))
    if not _worker_started:
        threading.Thread(target=_worker, daemon=True).start()
        _worker_started = True
    return action_id


def get_status(action_id: str) -> dict[str, object]:
    return ACTION_STATUS.get(action_id, {"status": "unknown"})


def expand_template(name: str, params: Mapping[str, object]) -> dict[str, object]:
    tpl = TEMPLATES.get(name)
    if not tpl:
        raise ValueError("Unknown template")
    if isinstance(tpl, str):
        tpl = tpl.format(**params)
        loaded = json.loads(tpl)
        return loaded if isinstance(loaded, dict) else {}
    out_obj = json.loads(json.dumps(tpl))  # deep copy
    out: dict[str, object] = out_obj if isinstance(out_obj, dict) else {}
    def expand(obj: object) -> object:
        if isinstance(obj, str):
            return obj.format(**params)
        if isinstance(obj, list):
            return [expand(item) for item in obj]
        if isinstance(obj, dict):
            return {key: expand(value) for key, value in obj.items()}
        return obj

    expanded = expand(out)
    return expanded if isinstance(expanded, dict) else {}


def template_placeholders(name: str) -> set[str]:
    """Return placeholder fields required by a template."""
    tpl = TEMPLATES.get(name)
    if not tpl:
        raise ValueError("Unknown template")
    import string

    def collect(obj: object) -> set[str]:
        keys: set[str] = set()
        if isinstance(obj, str):
            for _, field, _, _ in string.Formatter().parse(obj):
                if field:
                    keys.add(field)
        elif isinstance(obj, dict):
            for v in obj.values():
                keys.update(collect(v))
        elif isinstance(obj, list):
            for v in obj:
                keys.update(collect(v))
        return keys

    return collect(tpl)

def dispatch(intent: dict[str, Any]) -> dict[str, object]:
    itype_obj = intent.get("type")
    itype = str(itype_obj) if isinstance(itype_obj, str) else ""
    if itype == "template":
        name = str(intent.get("name", ""))
        params_obj = intent.get("params", {})
        params = params_obj if isinstance(params_obj, Mapping) else {}
        expanded = expand_template(name, params)
        return dispatch(expanded)
    act = ACTUATORS.get(itype)
    if not act:
        raise ValueError("Unsupported intent")
    return act.execute(intent)


LAST_EXECUTION: dict[tuple[str, str], float] = {}
RATE_LIMIT_SECONDS = int(os.getenv("ACT_RATE_LIMIT", "5"))


def _normalize_intent(intent: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = cast(Dict[str, Any], json.loads(json.dumps(intent)))
    if normalized.get("type") == "shell":
        argv, legacy_cmd = _canonical_shell_argv(normalized)
        normalized["argv"] = list(argv)
        if legacy_cmd is None:
            normalized.pop("cmd", None)
        else:
            normalized["legacy_cmd"] = legacy_cmd
            normalized.pop("cmd", None)
    return normalized


def _rate_limit(intent: Dict[str, Any], user: str | None) -> None:
    intent_type = str(intent.get("type", ""))
    intent_name = str(intent.get("name", ""))
    key = (user or "", f"{intent_type}:{intent_name}")
    now = time.time()
    last = LAST_EXECUTION.get(key, 0)
    if now - last < RATE_LIMIT_SECONDS:
        raise RuntimeError("Rate limit exceeded")
    LAST_EXECUTION[key] = now


CRITIQUE_STEPS: list[Callable[[Mapping[str, Any], Exception], str]] = [
    lambda i, e: f"Action {i.get('type')} failed with {e}. Try again with adjusted parameters.",
    lambda i, e: f"Repeated failure for {i.get('type')}. Verify permissions or inputs before retrying.",
    lambda i, e: f"Escalation: manual intervention required for {i.get('type')}" ,
]


def _auto_critique(intent: Dict[str, Any], error: Exception, step: int = 0) -> tuple[str, int]:
    """Return critique text and next step index."""
    idx = min(step, len(CRITIQUE_STEPS) - 1)
    critique = CRITIQUE_STEPS[idx](intent, error)
    next_step = idx + 1 if idx + 1 < len(CRITIQUE_STEPS) else idx
    return critique, next_step


def act(
    intent: Dict[str, Any],
    explanation: str | None = None,
    user: str | None = None,
    dry_run: bool | None = None,
    critique_step: int | None = None,
) -> Dict[str, Any]:
    """Execute an intent and persist a log entry.

    Parameters
    ----------
    intent: mapping describing the action. Keys depend on the ``type`` field.
    explanation: optional reason for choosing the action.
    """
    _authorize_effect()
    if dry_run is None:
        dry_run = bool(intent.get("dry_run", False))
    try:
        intent = _normalize_intent(intent)
        intent.pop("dry_run", None)
        from memory_manager import save_reflection, write_mem
        _rate_limit(intent, user)
        if dry_run:
            result = {"dry_run": True, "intent": intent}
        else:
            result = dispatch(intent)
        reflection_text = (
            f"Action {intent.get('type')} {'dry run' if dry_run else 'executed'} successfully"
        )
        log_entry = {
            "intent": intent,
            "result": result,
            "explanation": explanation or "",
            "user": user or "",
            "status": "finished",
            "reflection": reflection_text,
        }
        log_id = write_mem(json.dumps(log_entry), tags=["act", intent.get("type", "")], source="actuator")
        reflection_id = save_reflection(
            parent=log_id,
            intent=intent,
            result=result,
            reason=explanation or "",
            user=user or "",
            plugin=intent.get("type", ""),
        )
        result = dict(result)
        result.update({"log_id": log_id, "status": "finished", "reflection": reflection_text, "reflection_id": reflection_id})
        if explanation:
            result["explanation"] = explanation
        return result
    except Exception as e:  # pragma: no cover - defensive
        from memory_manager import save_reflection, write_mem
        reflection_text = f"Action {intent.get('type')} failed: {e}"
        step = critique_step if critique_step is not None else intent.pop("_critique_step", 0)
        critique, next_step = _auto_critique(intent, e, step)
        err_entry = {
            "intent": intent,
            "error": str(e),
            "explanation": explanation or "",
            "user": user or "",
            "status": "failed",
            "reflection": reflection_text,
        }
        log_id = write_mem(json.dumps(err_entry), tags=["act", "error"], source="actuator")
        reflection_id = save_reflection(
            parent=log_id,
            intent=intent,
            result=None,
            reason=str(e),
            next_step=critique,
            user=user or "",
            plugin=intent.get("type", ""),
        )
        return {
            "error": str(e),
            "log_id": log_id,
            "status": "failed",
            "reflection": reflection_text,
            "critique": critique,
            "critique_step": next_step,
            "reflection_id": reflection_id,
        }


def auto_call(
    intent: Dict[str, Any],
    explanation: str | None = None,
    *,
    trace: str | None = None,
) -> Dict[str, Any]:
    """Execute an intent and log it to the autonomous call history."""
    result = act(intent, explanation=explanation, user="auto")
    import autonomous_audit as aa
    aa.log_entry(
        action=json.dumps(intent),
        rationale=explanation or "auto_call",
        memory=[str(result.get("log_id"))] if result.get("log_id") else [],
        expected=str(result),
        why_chain=[
            "Auto-call dispatched intent", 
            "Auto-call invoked by autonomous subsystem", 
            "Fragment logged for trace"
        ],
    )
    entry = {
        "timestamp": time.time(),
        "intent": intent,
        "result": result,
        "trace": trace,
    }
    AUTONOMOUS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTONOMOUS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return result


def recent_logs(last: int = 10, reflect: bool = False) -> list[dict[str, object]]:
    from memory_manager import RAW_PATH, recent_reflections
    files = sorted(RAW_PATH.glob("*.json"))
    refl_map = {}
    if reflect:
        for r in recent_reflections(limit=last * 2):
            refl_map[r.get("parent")] = r
    out = []
    for fp in reversed(files):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "act" not in data.get("tags", []):
            continue
        try:
            entry = json.loads(data.get("text", "{}"))
            entry["timestamp"] = data.get("timestamp")
            entry["id"] = data.get("id")
            if "intent" not in entry:
                continue
            if reflect:
                entry["reflection_text"] = entry.get("reflection", "")
                if entry["id"] in refl_map:
                    r = refl_map[entry["id"]]
                    entry["reflection_text"] = (
                        r.get("reason") or r.get("next") or entry.get("reflection", "")
                    )
            out.append(entry)
            if len(out) >= last:
                break
        except Exception:
            continue
    return out


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="SentientOS actuator CLI")
    parser.add_argument(
        "subcommand",
        choices=[
            "shell",
            "http",
            "write",
            "email",
            "webhook",
            "template",
            "template_help",
            "logs",
            "templates",
        ],
        help="Action type",
    )
    parser.add_argument("cmd", nargs="?", help="Legacy simple command when subcommand=shell")
    parser.add_argument("--url", dest="url", help="URL for http")
    parser.add_argument("--method", dest="method", default="GET")
    parser.add_argument("--data", dest="data")
    parser.add_argument("--file", dest="file")
    parser.add_argument("--text", dest="text")
    parser.add_argument("--to", dest="to")
    parser.add_argument("--subject", dest="subject")
    parser.add_argument("--body", dest="body")
    parser.add_argument("--payload", dest="payload")
    parser.add_argument("--name", dest="name")
    parser.add_argument("--params", dest="params")
    parser.add_argument("--cwd", dest="cwd", default=".")
    parser.add_argument("--why", dest="why")
    parser.add_argument("--dry", action="store_true", help="Dry run")
    parser.add_argument("--reflect", action="store_true", help="Include reflections in logs")
    parser.add_argument("--last", dest="last", type=int, default=10)

    args = parser.parse_args(argv)

    if args.subcommand == "templates":
        names = list(TEMPLATES.keys())
        if args.cmd:
            term = args.cmd.lower()
            names = [n for n in names if term in n.lower()]
        print(json.dumps({"templates": names}, indent=2))
        return

    intent: Dict[str, Any] = {"type": args.subcommand if args.subcommand not in {"write", "logs"} else ("file" if args.subcommand == "write" else "logs")}
    if args.subcommand == "shell" and args.cmd:
        intent["cmd"] = args.cmd
        intent["cwd"] = args.cwd
    elif args.subcommand == "http":
        intent.update({"url": args.url or "", "method": args.method})
        if args.data:
            intent["data"] = args.data
    elif args.subcommand == "write":
        intent.update({"path": args.file or "", "content": args.text or ""})
    elif args.subcommand == "email":
        intent.update({"to": args.to or "", "subject": args.subject or "", "body": args.body or ""})
    elif args.subcommand == "webhook":
        payload = json.loads(args.payload or "{}") if args.payload else {}
        intent.update({"url": args.url or "", "payload": payload})
    elif args.subcommand == "template":
        params = json.loads(args.params or "{}") if args.params else {}
        missing = [p for p in template_placeholders(args.name or "") if p not in params]
        for m in missing:
            params[m] = input(f"{m}: ")
        intent.update({"name": args.name or "", "params": params})
    elif args.subcommand == "template_help":
        if args.name:
            fields = template_placeholders(args.name)
            example = {k: f"<{k}>" for k in fields}
            print(json.dumps({"required": sorted(fields), "example": example}, indent=2))
        else:
            print("Specify --name")
        return
    elif args.subcommand == "logs":
        logs = recent_logs(args.last, reflect=args.reflect)
        print(json.dumps(logs, indent=2))
        return

    out = act(intent, explanation=args.why, dry_run=args.dry)
    print(json.dumps(out))


if __name__ == "__main__":  # pragma: no cover - CLI execution
    main()
