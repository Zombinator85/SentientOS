"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import experiment_tracker as et
import reflex_manager as rm
from api import actuator


DATA_STREAMS = [
    get_log_path("emotion.jsonl"),
    get_log_path("eeg.jsonl"),
    get_log_path("haptics.jsonl"),
    get_log_path("bio.jsonl"),
    get_log_path("system.log"),
]

STATE_FILE = get_log_path("autonomous_state.json")


def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


state = _load_state()


def scan_streams() -> List[Dict[str, Any]]:
    """Return new signal events since last scan."""
    events: List[Dict[str, Any]] = []
    for fp in DATA_STREAMS:
        if not fp.exists():
            continue
        last_pos = state.get(fp.name, 0)
        try:
            with fp.open('r', encoding='utf-8') as f:
                f.seek(last_pos)
                for line in f:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
                state[fp.name] = f.tell()
        except Exception:
            continue
    _save_state(state)
    return events


def analyze_events(events: List[Dict[str, Any]]) -> None:
    for ev in events:
        stress = ev.get('stress', 0)
        beta = ev.get('beta', 0)
        if stress > 0.8 and beta > 0.8:
            exp_id = et.auto_propose_experiment(
                description='stress beta mitigation',
                conditions='stress>0.8 & beta>0.8',
                expected='reduced stress',
                signals=ev,
            )
            rule = rm.ReflexRule(
                rm.OnDemandTrigger(),
                [{'type': 'workflow', 'name': 'calm_down'}],
                name=f'autocalm_{exp_id}',
            )
            manager = rm.get_default_manager() or rm.ReflexManager()
            rm.set_default_manager(manager)
            manager.auto_generate_rule(rule.trigger, rule.actions, rule.name, signals=ev)
            actuator.auto_call({'type': 'workflow', 'name': 'calm_down'}, explanation='auto stress mitigation', trace=exp_id)


def run_loop(interval: float = 60.0) -> None:
    manager = rm.get_default_manager() or rm.ReflexManager()
    rm.set_default_manager(manager)
    manager.start()
    try:
        while True:
            events = scan_streams()
            if events:
                analyze_events(events)
            manager.auto_prune()
            time.sleep(interval)
    finally:
        manager.stop()


if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser(description='Autonomous operations loop')
    p.add_argument('--interval', type=float, default=60.0)
    args = p.parse_args()
    run_loop(args.interval)
