"""Read-only proof of the exact catalog in authenticated installation custody."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from sentientos.installation_state import InstallationStateError, InstallationStateHandle
from sentientos.local_model_catalog import LocalModelCatalogError, local_model_catalog_digest, validate_local_model_catalog
from sentientos.local_model_catalog_deployment import (
    SUCCESSFUL_FINALIZATION_OUTCOMES,
    verify_deployment_finalization,
    verify_deployment_receipt,
)
from sentientos.local_model_catalog_deployment_architecture import semantic_digest
from sentientos.model_catalog_custody import ModelCatalogCustody

PROOF_SCHEMA = "sentientos.local_model_catalog_consumer_proof:v1"
SUCCESSFUL_VALIDATION = "candidate_and_publication_evidence_verified"


class CatalogConsumerCustodyError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AuthoritativeCatalogSnapshot:
    """A coherent frozen-by-copy catalog and its immutable evidence projection."""

    catalog: dict[str, Any]
    proof: dict[str, Any]


def _mapping(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogConsumerCustodyError(code) from exc
    if not isinstance(value, dict):
        raise CatalogConsumerCustodyError(code)
    return value


def construct_authoritative_catalog_consumer_proof(
    handle: InstallationStateHandle,
) -> AuthoritativeCatalogSnapshot:
    """Reconstruct current provenance under the canonical catalog lock.

    Witness ordering is lexical identity ordering, not chronological recency.
    No state is created, changed, deployed, authorized, or acquired here.
    """
    try:
        custody = ModelCatalogCustody.for_installation(handle)
        with handle.exclusive_lock(custody.catalog_lock):
            raw_catalog = handle.read_regular(custody.authoritative_catalog)
            catalog = validate_local_model_catalog(_mapping(raw_catalog, "authoritative_catalog_malformed"))
            catalog_digest = local_model_catalog_digest(catalog)
            witnesses: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
            for name in handle.list_regular_names(custody.deployment_receipts):
                if not name.endswith(".json"):
                    raise CatalogConsumerCustodyError("deployment_receipt_name_invalid")
                receipt = _mapping(handle.read_regular(custody.deployment_receipts.child(name)),
                                   "deployment_receipt_malformed")
                if not verify_deployment_receipt(receipt) or name != f"{receipt.get('receipt_id')}.json":
                    raise CatalogConsumerCustodyError("deployment_receipt_invalid")
                if (receipt.get("installation_identity") != handle.identity.value
                        or receipt.get("custody_identity") != custody.custody_identity
                        or receipt.get("candidate_catalog_semantic_digest") != catalog_digest
                        or receipt.get("resulting_authoritative_catalog_semantic_digest") != catalog_digest):
                    continue  # valid immutable evidence for a different historical catalog
                if (receipt.get("validation_outcome") != SUCCESSFUL_VALIDATION
                        or receipt.get("final_state") != "deployed_verified"):
                    raise CatalogConsumerCustodyError("deployment_receipt_not_successful")
                transaction_id = receipt.get("transaction_id")
                if not isinstance(transaction_id, str) or not transaction_id.startswith("catalog-transaction-"):
                    raise CatalogConsumerCustodyError("deployment_transaction_identity_invalid")
                final = _mapping(handle.read_regular(custody.transactions.child(f"{transaction_id}.final.json")),
                                 "deployment_finalization_malformed")
                if (not verify_deployment_finalization(final)
                        or final.get("transaction_id") != transaction_id
                        or final.get("deployment_receipt_id") != receipt.get("receipt_id")
                        or final.get("deployment_receipt_semantic_digest") != receipt.get("receipt_semantic_digest")
                        or final.get("resulting_authoritative_catalog_semantic_digest") != catalog_digest
                        or final.get("terminal_outcome") not in SUCCESSFUL_FINALIZATION_OUTCOMES):
                    raise CatalogConsumerCustodyError("deployment_finalization_invalid")
                witnesses.append((str(receipt["receipt_id"]), transaction_id, receipt, final))
            if not witnesses:
                raise CatalogConsumerCustodyError("authoritative_catalog_witness_absent")
            _, transaction_id, receipt, final = sorted(witnesses, key=lambda item: item[:2])[0]
            proof = {
                "schema_version": PROOF_SCHEMA,
                "installation_identity": handle.identity.value,
                "custody_identity": custody.custody_identity,
                "authoritative_catalog_semantic_digest": catalog_digest,
                "deployment_receipt_id": receipt["receipt_id"],
                "deployment_receipt_semantic_digest": receipt["receipt_semantic_digest"],
                "resulting_catalog_digest": final["resulting_authoritative_catalog_semantic_digest"],
                "deployment_transaction_id": transaction_id,
                "transaction_final_state": final["terminal_outcome"],
                "authority_granted": False,
            }
            proof["proof_semantic_digest"] = semantic_digest(proof)
            return AuthoritativeCatalogSnapshot(deepcopy(catalog), proof)
    except CatalogConsumerCustodyError:
        raise
    except FileNotFoundError as exc:
        raise CatalogConsumerCustodyError("authoritative_catalog_evidence_absent") from exc
    except (InstallationStateError, LocalModelCatalogError, KeyError, TypeError, ValueError) as exc:
        raise CatalogConsumerCustodyError("authoritative_catalog_custody_invalid") from exc
