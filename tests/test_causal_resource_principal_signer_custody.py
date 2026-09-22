from __future__ import annotations

import ast
import base64
import hashlib
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import sentientos.causal_resource_principal_signer_custody as custody_module
from sentientos.causal_resource_principal_signer_custody import (
    OSKeyringRootIssuerPrivateKeyBackend,
    RootIssuerPrivateKeyCustody,
    RootIssuerPrivateKeyCustodyError,
    RootIssuerSigningKeyReference,
)

pytestmark = pytest.mark.no_legacy_skip
SEED = bytes(range(32))
ENCODED = base64.urlsafe_b64encode(SEED).rstrip(b"=")
ISSUER = "resource-principal-issuer"


def key_id(seed: bytes = SEED) -> str:
    public = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    return "ed25519-sha256:" + hashlib.sha256(public).hexdigest()


class Backend:
    def __init__(self, value: bytes = ENCODED) -> None:
        self.value = value
        self.returned: list[bytearray] = []
        self.calls = 0

    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        self.calls += 1
        result = bytearray(self.value)
        self.returned.append(result)
        return result


def configured(backend: object, *, signing_key_id: str | None = None) -> RootIssuerPrivateKeyCustody:
    return RootIssuerPrivateKeyCustody(
        reference=RootIssuerSigningKeyReference(
            ISSUER, signing_key_id or key_id(), "ed25519", "operator-key-v1"
        ),
        backend=backend,  # type: ignore[arg-type]
    )


def use(instance: RootIssuerPrivateKeyCustody, consumer: object = bytes) -> object:
    return instance.use_signing_material(
        issuer_id=ISSUER,
        signing_key_id=key_id(),
        algorithm="ed25519",
        consumer=consumer,  # type: ignore[arg-type]
    )


def test_exact_configured_tuple_exposes_readonly_32_byte_seed_then_zeroizes() -> None:
    backend = Backend()
    seen: list[tuple[bytes, bool]] = []
    def consume(view: memoryview) -> str:
        seen.append((bytes(view), view.readonly))
        return "used"

    result = use(configured(backend), consume)
    assert result == "used"
    assert seen == [(SEED, True)]
    assert backend.returned[0] == bytearray(len(ENCODED))


def test_each_use_reads_again_and_custody_does_not_cache_material() -> None:
    backend = Backend()
    instance = configured(backend)
    assert use(instance) == SEED
    assert use(instance) == SEED
    assert backend.calls == 2
    assert all(value == bytearray(len(ENCODED)) for value in backend.returned)
    assert SEED not in instance.__dict__.values()


def test_material_is_zeroized_when_consumer_raises() -> None:
    backend = Backend()

    def fail(view: memoryview) -> None:
        assert bytes(view) == SEED
        raise LookupError("consumer failure")

    with pytest.raises(LookupError, match="consumer failure"):
        use(configured(backend), fail)
    assert backend.returned[0] == bytearray(len(ENCODED))


@pytest.mark.parametrize(
    ("field", "value"),
    [("issuer_id", "other"), ("signing_key_id", "ed25519-sha256:" + "0" * 64),
     ("algorithm", "Ed25519"), ("algorithm", "ssh-ed25519")],
)
def test_unknown_or_unsupported_tuple_fails_before_backend(field: str, value: str) -> None:
    backend = Backend()
    kwargs = {"issuer_id": ISSUER, "signing_key_id": key_id(), "algorithm": "ed25519"}
    kwargs[field] = value
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_binding_mismatch$"):
        configured(backend).use_signing_material(**kwargs, consumer=bytes)
    assert backend.calls == 0


class RaisingBackend:
    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        raise OSError("sensitive backend detail")


def test_backend_failure_is_bounded_and_redacted() -> None:
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_backend_unavailable$") as caught:
        use(configured(RaisingBackend()))
    assert "sensitive" not in str(caught.value)


class MissingBackend:
    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        raise RootIssuerPrivateKeyCustodyError("signer_key_custody_secret_missing")


def test_missing_secret_is_bounded() -> None:
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_secret_missing$"):
        use(configured(MissingBackend()))


@pytest.mark.parametrize(
    "value",
    [b"!", ENCODED + b"=", ENCODED + b"\n", ENCODED + b"+", ENCODED + b"/",
     base64.urlsafe_b64encode(b"x" * 31).rstrip(b"="),
     base64.urlsafe_b64encode(b"x" * 64).rstrip(b"=")],
)
def test_noncanonical_or_wrong_length_material_fails_closed_and_zeroizes(value: bytes) -> None:
    backend = Backend(value)
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_material_invalid$"):
        use(configured(backend))
    assert backend.returned[0] == bytearray(len(value))


def test_private_seed_must_derive_configured_key_id() -> None:
    other_id = key_id(bytes(reversed(range(32))))
    backend = Backend()
    instance = configured(backend, signing_key_id=other_id)
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_key_id_mismatch$"):
        instance.use_signing_material(
            issuer_id=ISSUER, signing_key_id=other_id, algorithm="ed25519", consumer=bytes
        )
    assert backend.returned[0] == bytearray(len(ENCODED))


def test_mismatched_tuple_and_malformed_material_fail_closed() -> None:
    backend = Backend()
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_binding_mismatch$"):
        configured(backend).use_signing_material(
            issuer_id="other", signing_key_id=key_id(), algorithm="ed25519", consumer=bytes
        )
    assert backend.calls == 0
    malformed = Backend(ENCODED + b"=")
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_material_invalid$"):
        use(configured(malformed))
    assert malformed.returned[0] == bytearray(len(ENCODED) + 1)


def test_production_keyring_backend_uses_only_dedicated_exact_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    def get_password(service: str, account: str) -> str:
        calls.append((service, account))
        return ENCODED.decode()

    fake = SimpleNamespace(get_password=get_password)
    real_import = importlib.import_module
    monkeypatch.setattr("sentientos.causal_resource_principal_signer_custody.importlib.import_module", lambda name: fake if name == "keyring" else real_import(name))
    reference = RootIssuerSigningKeyReference(ISSUER, key_id(), "ed25519", "operator-key-v1")
    material = OSKeyringRootIssuerPrivateKeyBackend().read_configured(reference)
    assert material == ENCODED
    assert calls == [("sentientos.causal_resource_principal.root_issuer", "operator-key-v1")]
    assert not hasattr(fake, "set_password") and not hasattr(fake, "delete_password")


def test_production_keyring_missing_and_failure_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    reference = RootIssuerSigningKeyReference(ISSUER, key_id(), "ed25519", "operator-key-v1")
    monkeypatch.setattr("sentientos.causal_resource_principal_signer_custody.importlib.import_module", lambda name: SimpleNamespace(get_password=lambda *_: None))
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_secret_missing$"):
        OSKeyringRootIssuerPrivateKeyBackend().read_configured(reference)

    def unavailable(name: str) -> object:
        raise ImportError(name)
    monkeypatch.setattr("sentientos.causal_resource_principal_signer_custody.importlib.import_module", unavailable)
    with pytest.raises(RootIssuerPrivateKeyCustodyError, match="^signer_key_custody_backend_unavailable$"):
        OSKeyringRootIssuerPrivateKeyBackend().read_configured(reference)


def test_source_excludes_generation_admin_fallback_and_signer_capabilities() -> None:
    source = Path(custody_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert calls.isdisjoint({"generate", "set_password", "delete_password", "getenv", "open", "read_text", "sign", "sign_bytes", "authenticate_root_provenance"})
    assert "os.environ" not in source
    assert "nacl.signing" not in source
    assert "HmacTestStrategicSigner" not in source
    assert "SshStrategicSigner" not in source
    assert "KeyringBackend" not in source
    assert "sentientos.external_model" not in source
