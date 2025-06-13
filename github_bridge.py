"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""GitHub API bridge using ghapi with encrypted token storage."""

from logging_config import get_log_path
from typing import Any, Dict, Optional
from pathlib import Path
import json
import os

try:
    from ghapi.all import GhApi  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    GhApi = None  # type: ignore[misc]

try:
    from cryptography.fernet import Fernet  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    Fernet = None  # type: ignore[misc]

LOG_FILE = get_log_path("github_actions.jsonl", "GITHUB_ACTION_LOG")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
TOKEN_FILE = get_log_path("github_tokens.enc", "GITHUB_TOKEN_FILE")
KEY_FILE = get_log_path("github_tokens.key", "GITHUB_TOKEN_KEY_FILE")


class GitHubBridge:
    """Lightweight wrapper around ghapi with encrypted token storage."""

    def __init__(self, *, token_file: Path = TOKEN_FILE, key_file: Path = KEY_FILE) -> None:
        self.token_file = Path(token_file)
        self.key_file = Path(key_file)
        self.cipher = self._load_cipher()
        self.tokens: Dict[str, str] = self._load_tokens()
        self._apis: Dict[str, Any] = {}

    # -- Token handling -------------------------------------------------
    def _load_cipher(self) -> Optional[Fernet]:
        if Fernet is None:
            return None
        if self.key_file.exists():
            key = self.key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
        return Fernet(key)

    def _load_tokens(self) -> Dict[str, str]:
        if not self.token_file.exists() or self.cipher is None:
            return {}
        try:
            data = self.cipher.decrypt(self.token_file.read_bytes())
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {}

    def _save_tokens(self) -> None:
        if self.cipher is None:
            return
        data = json.dumps(self.tokens).encode("utf-8")
        enc = self.cipher.encrypt(data)
        self.token_file.write_bytes(enc)

    def set_token(self, model: str, token: str) -> None:
        """Store encrypted token for a model."""
        self.tokens[model] = token
        self._save_tokens()

    def _api(self, model: str) -> Any:
        token = self.tokens.get(model)
        if token is None:
            raise RuntimeError(f"Token for {model} not set")
        api = self._apis.get(model)
        if api is None:
            if GhApi is None:
                raise RuntimeError("ghapi not available")
            self._apis[model] = api = GhApi(token=token)
        return api

    def _log(self, action: str, data: Dict[str, Any]) -> None:
        entry = {"action": action, **data}
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # -- Core methods ---------------------------------------------------
    def search_code(self, query: str, *, model: str = "default", **kwargs: Any) -> Any:
        api = self._api(model)
        self._log("search_code", {"query": query, "model": model})
        return api.search.code(q=query, **kwargs)

    def create_issue(self, repo: str, title: str, body: str, *, model: str = "default", **kwargs: Any) -> Any:
        owner, repo_name = repo.split("/")
        api = self._api(model)
        self._log("create_issue", {"repo": repo, "title": title, "model": model})
        return api.issues.create(owner, repo_name, title=title, body=body, **kwargs)

    def create_pr(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
        *,
        model: str = "default",
        **kwargs: Any,
    ) -> Any:
        owner, repo_name = repo.split("/")
        api = self._api(model)
        self._log(
            "create_pr",
            {"repo": repo, "title": title, "head": head, "base": base, "model": model},
        )
        return api.pulls.create(owner, repo_name, title=title, body=body, head=head, base=base, **kwargs)

