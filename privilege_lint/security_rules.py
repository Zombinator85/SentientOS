from __future__ import annotations

import re
from pathlib import Path

_KEY_PATTERNS = {
    'aws': re.compile(r'AKIA[0-9A-Z]{16}'),
    'gcp': re.compile(r'AIza[0-9A-Za-z_-]{35}'),
    'azure': re.compile(r'AccountKey=[0-9A-Za-z+/=]{20,}'),
}

_SHELL_RE = re.compile(r'subprocess\.[A-Za-z]*\([^\n]*shell=True')
_PICKLE_RE = re.compile(r'pickle\.loads\(')
_CHMOD_RE = re.compile(r'chmod\([^,]+,\s*0o?777')


def validate_security(lines: list[str], path: Path) -> dict[str, list[str]]:
    text = "\n".join(lines)
    issues_key: list[str] = []
    issues_call: list[str] = []
    for name, pat in _KEY_PATTERNS.items():
        for m in pat.finditer(text):
            ln = text[:m.start()].count('\n') + 1
            issues_key.append(f"{path}:{ln} security-key {name} pattern")
    for regex, msg in [(_SHELL_RE, 'shell-true'), (_PICKLE_RE, 'pickle-loads'), (_CHMOD_RE, 'chmod-777')]:
        for m in regex.finditer(text):
            ln = text[:m.start()].count('\n') + 1
            issues_call.append(f"{path}:{ln} security-call {msg}")
    return {"security-key": issues_key, "security-call": issues_call}
