from __future__ import annotations

from sentientos.forge_failures import FailureCluster, FailureSignature, HarvestResult
from sentientos.forge_progress import delta, snapshot_from_harvest


def _cluster(nodeid: str, error_type: str, message_digest: str) -> FailureCluster:
    return FailureCluster(
        signature=FailureSignature(
            nodeid=nodeid,
            file=nodeid.split("::")[0],
            line=None,
            test_name=nodeid.split("::")[-1],
            error_type=error_type,
            message_digest=message_digest,
        ),
        count=1,
        examples=["x"],
    )


def test_delta_marks_improved_when_failed_count_drops() -> None:
    prev = snapshot_from_harvest(
        HarvestResult(total_failed=2, clusters=[_cluster("tests/test_a.py::test_one", "AssertionError", "a")], raw_excerpt_truncated="")
    )
    cur = snapshot_from_harvest(
        HarvestResult(total_failed=1, clusters=[_cluster("tests/test_a.py::test_one", "AssertionError", "a")], raw_excerpt_truncated="")
    )

    change = delta(prev, cur)

    assert change.improved is True
    assert change.failed_count_delta == -1


def test_delta_marks_improved_when_digest_changes_without_count_drop() -> None:
    prev = snapshot_from_harvest(
        HarvestResult(total_failed=1, clusters=[_cluster("tests/test_a.py::test_one", "AssertionError", "a")], raw_excerpt_truncated="")
    )
    cur = snapshot_from_harvest(
        HarvestResult(total_failed=1, clusters=[_cluster("tests/test_a.py::test_one", "AssertionError", "b")], raw_excerpt_truncated="")
    )

    change = delta(prev, cur)

    assert change.cluster_digest_changed is True
    assert change.improved is True
