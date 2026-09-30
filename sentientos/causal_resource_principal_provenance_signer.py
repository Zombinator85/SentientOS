"""Purpose-scoped Ed25519 authentication of one canonical root principal.

This module can emit only issuer-provenance evidence.  It has no arbitrary-message
signing, issuance, trust administration, allocation, admission, or effect surface.
"""
from __future__ import annotations

import base64
import importlib
from typing import Any, Callable

from sentientos.causal_resource_principal import (
    CausalResourcePrincipal,
    CausalResourcePrincipalError,
    CausalResourcePrincipalVerifier,
)
from sentientos.causal_resource_principal_authentication import (
    ED25519_ALGORITHM,
    RootIssuerProvenanceError,
    RootPrincipalIssuerProvenance,
    canonical_root_provenance_payload,
)
from sentientos.causal_resource_principal_signer_custody import (
    RootIssuerPrivateKeyCustody,
    RootIssuerPrivateKeyCustodyError,
    RootIssuerSigningKeyReference,
)


class RootIssuerProvenanceSigningError(RuntimeError):
    """A bounded, redacted failure at the purpose-scoped signing boundary."""


def _load_private_key_type() -> Any:
    try:
        module = importlib.import_module(
            "cryptography.hazmat.primitives.asymmetric.ed25519"
        )
        return module.Ed25519PrivateKey
    except (ImportError, AttributeError) as exc:
        raise RootIssuerProvenanceSigningError(
            "root_provenance_signing_backend_unavailable"
        ) from exc


class CryptographyEd25519RootIssuerProvenanceSigner:
    """Sign only the canonical provenance payload for an exact canonical root."""

    def __init__(
        self,
        *,
        reference: RootIssuerSigningKeyReference,
        custody: RootIssuerPrivateKeyCustody,
        private_key_type_loader: Callable[[], Any] = _load_private_key_type,
    ) -> None:
        self._reference = reference
        self._custody = custody
        self._private_key_type_loader = private_key_type_loader

    def authenticate_root_provenance(
        self, principal: CausalResourcePrincipal, *, signed_at: str
    ) -> RootPrincipalIssuerProvenance:
        if type(principal) is not CausalResourcePrincipal:
            raise RootIssuerProvenanceSigningError("root_principal_not_canonical")
        reference = self._reference
        if reference.algorithm != ED25519_ALGORITHM:
            raise RootIssuerProvenanceSigningError("root_provenance_algorithm_unsupported")
        try:
            verified = CausalResourcePrincipalVerifier().verify(
                principal,
                current_time=signed_at,
                expected_issuer_id=reference.issuer_id,
            )
        except (CausalResourcePrincipalError, TypeError, ValueError) as exc:
            raise RootIssuerProvenanceSigningError("root_principal_not_signable") from exc

        payload = canonical_root_provenance_payload(
            principal_id=verified.principal_id,
            principal_binding_digest=verified.binding_digest,
            issuer_id=reference.issuer_id,
            signing_key_id=reference.signing_key_id,
            algorithm=ED25519_ALGORITHM,
            signed_at=signed_at,
        )

        def sign_exact_payload(seed: memoryview) -> bytes:
            try:
                private_key_type = self._private_key_type_loader()
                signature = private_key_type.from_private_bytes(bytes(seed)).sign(payload)
            except RootIssuerProvenanceSigningError:
                raise
            except Exception as exc:
                raise RootIssuerProvenanceSigningError(
                    "root_provenance_signing_failed"
                ) from exc
            if not isinstance(signature, bytes) or len(signature) != 64:
                raise RootIssuerProvenanceSigningError("root_provenance_signing_failed")
            return signature

        try:
            signature = self._custody.use_signing_material(
                issuer_id=reference.issuer_id,
                signing_key_id=reference.signing_key_id,
                algorithm=ED25519_ALGORITHM,
                consumer=sign_exact_payload,
            )
        except RootIssuerProvenanceSigningError:
            raise
        except RootIssuerPrivateKeyCustodyError as exc:
            raise RootIssuerProvenanceSigningError(str(exc)) from exc
        encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        try:
            return RootPrincipalIssuerProvenance.create(
                principal_id=verified.principal_id,
                principal_binding_digest=verified.binding_digest,
                issuer_id=reference.issuer_id,
                signing_key_id=reference.signing_key_id,
                algorithm=ED25519_ALGORITHM,
                signed_at=signed_at,
                signature=encoded,
            )
        except RootIssuerProvenanceError as exc:
            raise RootIssuerProvenanceSigningError(
                "root_provenance_envelope_invalid"
            ) from exc


__all__ = [
    "CryptographyEd25519RootIssuerProvenanceSigner",
    "RootIssuerProvenanceSigningError",
]
