from __future__ import annotations

import hashlib
import ssl
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

from scripts.gaming_companion_cross_host_smoke import (
    _contexts,
    _private_ip,
    _test_identities,
)

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("address", ["127.0.0.1", "8.8.8.8", "169.254.1.1"])
def test_cross_host_smoke_rejects_loopback_public_and_link_local(address: str) -> None:
    with pytest.raises(ValueError, match="private_host_address_unavailable"):
        _private_ip(address)


def test_cross_host_smoke_test_credentials_are_distinct_and_mutually_usable(
        tmp_path: Path) -> None:
    identities = _test_identities(tmp_path)
    ca = identities["ca"]
    wsl, windows = identities["wsl"], identities["windows"]

    assert _private_ip("172.18.1.2") == "172.18.1.2"
    assert wsl["pin"] != windows["pin"]
    for identity in (wsl, windows):
        cert = x509.load_pem_x509_certificate(identity["cert"].read_bytes())
        assert hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest() == identity["pin"]
        server, client = _contexts(ca, identity["cert"], identity["key"])
        assert server.verify_mode == ssl.CERT_REQUIRED
        assert client.check_hostname is True
