import json
from typing import List, Dict, Optional
from sentient_banner import print_banner, print_closing
import federation_log as fl
import ledger

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore

import love_treasury as lt

def announce_payload() -> List[Dict[str, object]]:
    """Return metadata about local enshrined logs for federation."""
    print_banner()
    data = lt.federation_metadata()
    fl.add("local", message="announce payload")
    print_closing()
    return data

def import_payload(payload: List[Dict[str, object]], origin: str) -> List[str]:
    """Import logs from a federation payload."""
    print_banner()
    fl.add(origin, message="import payload")
    imported: List[str] = []
    for entry in payload:
        if lt.import_federated(entry, origin=origin):
            imported.append(entry.get("id"))
    if imported:
        fl.add(origin, message="imported logs")
    print_closing()
    return imported

def pull(base_url: str) -> List[str]:
    """Pull logs from a remote cathedral via HTTP."""
    if requests is None:
        raise RuntimeError("requests module not available")
    url = base_url.rstrip("/")
    fl.add(url, message="sync start")
    r = requests.get(f"{url}/federation/announce", timeout=10)
    r.raise_for_status()
    metas = r.json()
    imported: List[str] = []
    for meta in metas:
        lid = meta.get("id")
        if not lid:
            continue
        r2 = requests.get(f"{url}/federation/export/{lid}", timeout=10)
        if r2.status_code != 200:
            continue
        data = r2.json()
        if lt.import_federated(data, origin=url):
            imported.append(lid)
    if imported:
        fl.add(url, message="sync completed")
    print_closing()
    return imported


def invite(
    peer: str,
    email: str = "",
    message: str = "federation invite",
    blessing: str = "",
    supporter: str = "",
    affirm: bool = False,
) -> Dict[str, str]:
    """Record a federation invite blessing and optional affirmation."""
    print_banner()
    entry = fl.add(peer, email=email, message=message)
    ledger.log_support(supporter or peer, blessing or message)
    if affirm:
        ledger.log_federation(peer, email=email, message="affirmation")
    print_closing()
    return entry
