import pytest

from resident_kernel import (
    KernelInvariantError,
    KernelMisuseError,
    KernelWriteOutsideEpochError,
    ResidentKernel,
)


def test_update_requires_epoch() -> None:
    kernel = ResidentKernel()
    with pytest.raises(KernelWriteOutsideEpochError):
        kernel.update_governance("governance_arbiter", system_phase="ready")


def test_authorized_update_inside_epoch_succeeds() -> None:
    kernel = ResidentKernel()
    with kernel.begin_epoch("tick") as epoch:
        kernel.update_governance("governance_arbiter", system_phase="ready")
    audit = epoch.audit_record
    assert audit is not None
    assert audit.epoch_id == 1
    assert "system_phase" in audit.fields_touched


def test_epoch_increments_on_end() -> None:
    kernel = ResidentKernel()
    with kernel.begin_epoch("tick"):
        kernel.update_governance("governance_arbiter", system_phase="ready")
    assert kernel.governance_view().kernel_epoch == 1


def test_nested_epoch_forbidden() -> None:
    kernel = ResidentKernel()
    session = kernel.begin_epoch("outer")
    try:
        with pytest.raises(KernelMisuseError):
            kernel.begin_epoch("inner")
    finally:
        kernel.end_epoch()
    assert session.audit_record is None


def test_checkpoint_hash_changes_with_epoch() -> None:
    kernel = ResidentKernel()
    with kernel.begin_epoch("snapshot-a"):
        checkpoint_a = kernel.create_checkpoint()
    with kernel.begin_epoch("tick"):
        pass
    with kernel.begin_epoch("snapshot-b"):
        checkpoint_b = kernel.create_checkpoint()
    assert checkpoint_a.digest != checkpoint_b.digest


def test_restore_rejects_epoch_regression() -> None:
    kernel = ResidentKernel()
    with kernel.begin_epoch("tick"):
        kernel.update_governance("governance_arbiter", system_phase="ready")
        checkpoint = kernel.create_checkpoint()
    with kernel.begin_epoch("advance"):
        pass
    with kernel.begin_epoch("restore"):
        kernel.pause_epoch()
        with pytest.raises(KernelInvariantError):
            kernel.restore_checkpoint(checkpoint)


def test_checkpoint_requires_epoch() -> None:
    kernel = ResidentKernel()
    with pytest.raises(KernelWriteOutsideEpochError):
        kernel.create_checkpoint()


def test_checkpoint_blocks_duplicate_epoch() -> None:
    kernel = ResidentKernel()
    with kernel.begin_epoch("tick"):
        kernel.update_governance("governance_arbiter", system_phase="ready")
        first = kernel.create_checkpoint()
        kernel.update_embodiment("governance_arbiter", kernel_seq=1, kernel_time=1)
        with pytest.raises(KernelMisuseError):
            kernel.create_checkpoint()
    assert first.governance["system_phase"] == "ready"


def test_restore_blocked_during_active_epoch() -> None:
    kernel = ResidentKernel()
    with kernel.begin_epoch("tick"):
        checkpoint = kernel.create_checkpoint()
    with kernel.begin_epoch("restore"):
        with pytest.raises(KernelMisuseError):
            kernel.restore_checkpoint(checkpoint)
