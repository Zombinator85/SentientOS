"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""GitHub API bridge using ghapi with keyring token storage and scope validation."""

from logging_config import get_log_path
from typing import Any, Dict, Iterable, Optional, cast
import json

try:
    from ghapi.all import GhApi
except Exception:  # pragma: no cover - optional dependency
    GhApi = None

keyring: Optional[Any]
try:
    import keyring as _keyring
    keyring = _keyring
except Exception:  # pragma: no cover - optional dependency
    keyring = None

LOG_FILE = get_log_path("github_actions.jsonl", "GITHUB_ACTION_LOG")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

KEYRING_SERVICE = "sentientos.github"


class GitHubBridge:
    """Lightweight wrapper around ghapi with keyring token storage."""

    def __init__(self, *, service: str = KEYRING_SERVICE) -> None:
        self.service = service
        self._apis: Dict[str, Any] = {}

    # -- Token handling -------------------------------------------------
    def _token_for(self, model: str) -> str | None:
        if keyring is None:
            return None
        return cast(Optional[str], keyring.get_password(self.service, model))

    def _save_token(self, model: str, token: str) -> None:
        if keyring is not None:
            keyring.set_password(self.service, model, token)

    def _check_scopes(self, token: str) -> list[str]:
        if GhApi is None:
            return []
        api = GhApi(token=token)
        try:
            api.users.get_authenticated()
        except Exception:
            return []
        hdr = getattr(api, "recv_hdrs", {}).get("X-OAuth-Scopes", "")
        return [s.strip() for s in hdr.split(",") if s.strip()]

    def set_token(self, model: str, token: str, scopes: Iterable[str] | None = None) -> None:
        """Validate and store a token for a model in the system keyring."""
        required = set(scopes or [])
        if required:
            avail = set(self._check_scopes(token))
            missing = sorted(required - avail)
            if missing:
                raise ValueError(f"Token missing scopes: {', '.join(missing)}")
        self._save_token(model, token)
        self._apis.pop(model, None)

    def _api(self, model: str) -> Any:
        token = self._token_for(model)
        if not token:
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

