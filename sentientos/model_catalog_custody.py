"""Narrow model-catalog custody projection; no deployment behavior or authority."""
from __future__ import annotations

from dataclasses import dataclass

from sentientos.installation_state import InstallationStateHandle, InstallationStateObject
from sentientos.local_model_catalog_deployment_architecture import (
    AUTHORITATIVE_CATALOG,
    AUTHORITATIVE_CUSTODY_KIND,
    CATALOG_DOMAIN,
    CATALOG_LOCK,
    DEPLOYMENT_RECEIPTS,
    TRANSACTIONS,
)


@dataclass(frozen=True)
class ModelCatalogCustody:
    installation: InstallationStateHandle
    custody_identity: str
    domain: InstallationStateObject
    authoritative_catalog: InstallationStateObject
    catalog_lock: InstallationStateObject
    transactions: InstallationStateObject
    deployment_receipts: InstallationStateObject

    @classmethod
    def for_installation(cls, handle: InstallationStateHandle) -> "ModelCatalogCustody":
        if not isinstance(handle, InstallationStateHandle):
            raise TypeError("authenticated installation state handle required")
        return cls(
            installation=handle,
            custody_identity=f"{AUTHORITATIVE_CUSTODY_KIND}:{handle.identity.value}",
            domain=handle.fixed_object(CATALOG_DOMAIN),
            authoritative_catalog=handle.fixed_object(AUTHORITATIVE_CATALOG),
            catalog_lock=handle.fixed_object(CATALOG_LOCK),
            transactions=handle.fixed_object(TRANSACTIONS),
            deployment_receipts=handle.fixed_object(DEPLOYMENT_RECEIPTS),
        )

    def initialize_directories(self) -> None:
        """Create only fixed custody directories; this does not deploy a catalog."""
        self.installation.ensure_directory(self.domain)
        self.installation.ensure_directory(self.transactions)
        self.installation.ensure_directory(self.deployment_receipts)
