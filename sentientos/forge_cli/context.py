from __future__ import annotations

from dataclasses import dataclass

from sentientos.cathedral_forge import CathedralForge
from sentientos.contract_sentinel import ContractSentinel
from sentientos.forge_merge_train import ForgeMergeTrain
from sentientos.forge_queue import ForgeQueue


@dataclass(frozen=True)
class ForgeContext:
    forge: CathedralForge
    queue: ForgeQueue
    merge_train: ForgeMergeTrain
    sentinel: ContractSentinel


def build_context() -> ForgeContext:
    forge = CathedralForge()
    queue = ForgeQueue()
    pulse_queue = ForgeQueue(pulse_root=forge.repo_root / "pulse")
    return ForgeContext(
        forge=forge,
        queue=queue,
        merge_train=ForgeMergeTrain(repo_root=forge.repo_root, queue=pulse_queue),
        sentinel=ContractSentinel(repo_root=forge.repo_root, queue=pulse_queue),
    )
