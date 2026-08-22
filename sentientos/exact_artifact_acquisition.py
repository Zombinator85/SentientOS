"""Private mechanics for acquiring an exact, already-authorized artifact.

This module deliberately has no product policy.  Callers supply the trusted
initial/redirect hosts, the exact byte identity, and a destination stream.
"""
from __future__ import annotations

import hashlib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, BinaryIO, Mapping, Protocol
from urllib.parse import urljoin, urlsplit

CHUNK_SIZE = 1024 * 1024


class ExactArtifactError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass
class StreamResponse:
    stream: BinaryIO
    headers: Mapping[str, str]
    destination_hosts: tuple[str, ...]
    redirect_count: int


class Transport(Protocol):
    def __call__(self, url: str) -> StreamResponse: ...


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, maximum: int, allowed_hosts: frozenset[str], error_code: str):
        self.maximum, self.allowed_hosts, self.error_code = maximum, allowed_hosts, error_code
        self.hosts: list[str] = []
        self.count = 0

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        url = urljoin(req.full_url, newurl)
        parsed = urlsplit(url)
        if self.count >= self.maximum:
            raise ExactArtifactError("redirect_limit_exceeded")
        if parsed.scheme != "https":
            raise ExactArtifactError("redirect_https_required")
        if parsed.hostname not in self.allowed_hosts:
            raise ExactArtifactError(self.error_code)
        self.count += 1
        self.hosts.append(str(parsed.hostname))
        return super().redirect_request(req, fp, code, msg, headers, url)


def https_transport(url: str, *, initial_hosts: frozenset[str], redirect_hosts: frozenset[str],
                    redirect_error: str = "redirect_host_rejected", max_redirects: int = 5,
                    timeout: float = 30.0) -> StreamResponse:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.hostname not in initial_hosts:
        raise ExactArtifactError("untrusted_source")
    handler = _RedirectHandler(max_redirects, redirect_hosts, redirect_error)
    opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        response = opener.open(urllib.request.Request(url, headers={"Accept-Encoding": "identity"}), timeout=timeout)
    except ExactArtifactError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise ExactArtifactError("network_error") from exc
    final_host = str(urlsplit(response.geturl()).hostname)
    return StreamResponse(response, dict(response.headers.items()),
                          tuple(dict.fromkeys([str(parsed.hostname), *handler.hosts, final_host])), handler.count)


def stream_exact(response: StreamResponse, output: BinaryIO, *, expected_size: int,
                 expected_sha256: str, size_error: str, hash_error: str) -> tuple[int, str]:
    """Copy bounded opaque bytes, verifying size and SHA before returning."""
    length = response.headers.get("Content-Length") or response.headers.get("content-length")
    if length is not None and (not length.isdigit() or int(length) != expected_size):
        raise ExactArtifactError(size_error)
    observed = 0
    digest = hashlib.sha256()
    while True:
        chunk = response.stream.read(CHUNK_SIZE)
        if not chunk:
            break
        offset = 0
        while offset < len(chunk):
            written = output.write(chunk[offset:])
            if not isinstance(written, int) or isinstance(written, bool) or written <= 0 or written > len(chunk) - offset:
                raise ExactArtifactError("artifact_write_error")
            persisted = chunk[offset:offset + written]
            observed += written
            if observed > expected_size:
                raise ExactArtifactError(size_error)
            digest.update(persisted)
            offset += written
    if observed != expected_size:
        raise ExactArtifactError(size_error)
    observed_hash = digest.hexdigest()
    if observed_hash != expected_sha256:
        raise ExactArtifactError(hash_error)
    return observed, observed_hash
