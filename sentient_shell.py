"""Sentient Script shell and compiler."""
from __future__ import annotations

import argparse
import json
import os
import readline
import shlex
import sys
import uuid
from typing import Any, Dict, Iterable, List
from urllib import request

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from sentientscript import SentientScriptInterpreter, ScriptSigner


_COMMAND_CATALOG: Dict[str, Dict[str, Any]] = {
    "dream.new": {
        "capability": "relay.dream",
        "params": ["goal"],
        "description": "Queue a new dream goal",
    },
    "relay.echo": {
        "capability": "relay.echo",
        "params": ["text"],
        "description": "Echo data through the relay",
    },
    "actuator.shell": {
        "capability": "actuator.shell",
        "params": ["cmd", "cwd"],
        "description": "Execute a shell command via the actuator",
    },
}


def _parse_assignments(tokens: Iterable[str]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("\"") and value.endswith("\""):
            value = value[1:-1]
        params[key] = value
    return params


def compile_command(command: str, *, seed: int | None = None) -> Dict[str, Any]:
    command = command.strip()
    if not command:
        raise ValueError("command required")
    tokens = shlex.split(command)
    if not tokens:
        raise ValueError("command required")
    action = tokens[0]
    spec = _COMMAND_CATALOG.get(action)
    if spec is None:
        raise ValueError(f"unknown command: {action}")
    params = _parse_assignments(tokens[1:])
    script_id = f"script-{uuid.uuid4().hex[:8]}"
    script = {
        "id": script_id,
        "version": "1.0",
        "seed": seed if seed is not None else int.from_bytes(os.urandom(4), "big"),
        "timeout": 30.0,
        "gas": 64,
        "capabilities": [spec["capability"]],
        "metadata": {"command": action, "compiled_from": command},
        "steps": [
            {
                "type": "action",
                "name": action,
                "params": params,
            }
        ],
    }
    return script


def _command_completer(text: str, state: int) -> str | None:
    options: List[str] = []
    buffer = readline.get_line_buffer()
    if not buffer or buffer.strip() == "":
        options = list(_COMMAND_CATALOG.keys())
    else:
        tokens = buffer.split()
        if len(tokens) == 1 and not buffer.endswith(" "):
            options = [name for name in _COMMAND_CATALOG if name.startswith(text)]
        else:
            action = tokens[0]
            spec = _COMMAND_CATALOG.get(action, {})
            params = spec.get("params", [])
            for param in params:
                candidate = f"{param}="
                if candidate.startswith(text):
                    options.append(candidate)
    options.sort()
    if state < len(options):
        return options[state]
    return None


def _send_to_relay(relay_url: str, script: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps({"script": script}).encode("utf-8")
    req = request.Request(relay_url.rstrip("/") + "/admin/scripts", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with request.urlopen(req) as resp:  # type: ignore[arg-type]
        body = resp.read().decode("utf-8")
        return json.loads(body)


def _interactive_loop(args: argparse.Namespace, interpreter: SentientScriptInterpreter, signer: ScriptSigner) -> int:
    print("Sentient Shell ready. Type 'exit' to quit.")
    while True:
        try:
            line = input("sentient> ")
        except EOFError:
            print()
            break
        line = line.strip()
        if not line:
            continue
        if line in {"exit", "quit"}:
            break
        try:
            script = compile_command(line, seed=args.seed)
        except ValueError as exc:
            print(f"error: {exc}")
            continue
        signer.sign(script)
        if args.run:
            result = interpreter.execute(script)
            print(json.dumps(result.outputs, indent=2, ensure_ascii=False))
        elif args.relay:
            try:
                response = _send_to_relay(args.relay, script)
            except Exception as exc:  # pragma: no cover - relay network issues
                print(f"relay error: {exc}")
            else:
                print(json.dumps(response, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(script, indent=2, ensure_ascii=False))
    return 0


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile commands into Sentient Scripts")
    parser.add_argument("command", nargs="*", help="Command to compile, e.g. dream.new goal=\"Rest\"")
    parser.add_argument("--relay", help="Relay base URL to POST the script to /admin/scripts")
    parser.add_argument("--run", action="store_true", help="Execute locally using the interpreter")
    parser.add_argument("--seed", type=int, help="Explicit RNG seed for deterministic scripts")
    parser.add_argument("--no-sign", action="store_true", help="Do not sign the compiled script")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    interpreter = SentientScriptInterpreter()
    signer = ScriptSigner(interpreter.signer._registry)  # reuse same registry
    readline.set_completer(_command_completer)
    readline.parse_and_bind("tab: complete")
    command_text = " ".join(args.command).strip()
    if not command_text:
        return _interactive_loop(args, interpreter, signer)
    try:
        script = compile_command(command_text, seed=args.seed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not args.no_sign:
        signer.sign(script)
    if args.run:
        result = interpreter.execute(script)
        print(json.dumps(result.outputs, indent=2, ensure_ascii=False))
        return 0
    if args.relay:
        response = _send_to_relay(args.relay, script)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(script, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
