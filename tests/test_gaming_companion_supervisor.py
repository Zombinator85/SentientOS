from __future__ import annotations

import threading
import queue
import hashlib
import time
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from types import SimpleNamespace

import pytest

from sentientos.gaming_companion_bridge import CompanionBridgeError
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver, encode_message
from sentientos.foreground_game_bridge import BridgeForegroundGameDetector
from sentientos.gaming_companion_supervisor import CompanionBridgeSupervisor
from sentientos.gaming_companion_tls_transport import BridgeGenerationCustodyRecord, BridgeGenerationPair

pytestmark = pytest.mark.no_legacy_skip


def _record(source_id: str, generation_id: str, key_reference: str,
            number: int, predecessor: str | None) -> BridgeGenerationCustodyRecord:
    return BridgeGenerationCustodyRecord(
        source_id=source_id,
        generation_id=generation_id,
        key_reference=key_reference,
        issuer_id="operator-custody",
        issued_at=f"2026-11-02T00:00:0{number}+00:00",
        authority_receipt_digest=f"{number:064x}" if source_id == "renderer" else f"{number + 100:064x}",
        predecessor_generation_id=predecessor,
    )


def _generation(number: int) -> BridgeGenerationPair:
    return BridgeGenerationPair(
        source=_record("renderer", f"generation-{number}", f"vault://renderer/key-{number}",
                       number, f"generation-{number - 1}" if number > 1 else None),
        acknowledgment=_record("sentientos-core", f"core-generation-{number}",
            f"vault://core/key-{number}", number,
            f"core-generation-{number - 1}" if number > 1 else None),
    )


@dataclass
class _Runtime:
    number: int
    started: bool = False
    closed: bool = False
    messages: queue.Queue = field(default_factory=queue.Queue)

    def start(self) -> int:
        self.started = True
        self.closed = False
        return 4000 + self.number

    def close(self) -> None:
        self.closed = True
        self.started = False

    def status(self) -> SimpleNamespace:
        return SimpleNamespace(running=self.started and not self.closed)

    def receive(self, timeout: float | None = None):
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise CompanionBridgeError("bridge_receive_timeout") from exc

    def supervisor_identity_bindings(self) -> tuple[dict[str, str], str, str]:
        return ({"renderer": f"generation-{self.number}"}, "sentientos-core",
                f"core-generation-{self.number}")


def test_supervisor_recovers_only_with_verified_successor_generation() -> None:
    runtimes: list[_Runtime] = []
    previous_records: list[BridgeGenerationPair | None] = []

    def factory(previous: BridgeGenerationPair | None):
        previous_records.append(previous)
        number = len(runtimes) + 1
        runtime = _Runtime(number)
        runtimes.append(runtime)
        return runtime, _generation(number)

    supervisor = CompanionBridgeSupervisor(
        runtime_factory=factory,
        authority_receipt_verifier=lambda digest, record: digest == record.authority_receipt_digest,
        max_restarts=1,
        poll_interval_seconds=0.01,
        backoff_base_seconds=0.01,
    )
    assert supervisor.start().generation_id == "generation-1"
    runtimes[0].close()  # failure injection; monitor must use a fresh authority record
    deadline = time.monotonic() + 1
    while supervisor.status().generation_id != "generation-2" and time.monotonic() < deadline:
        time.sleep(0.01)
    status = supervisor.status()
    assert status.state == "running"
    assert status.restart_count == 1
    assert status.listener_port == 4002
    assert status.acknowledgment_generation_id == "core-generation-2"
    assert previous_records == [None, _generation(1)]
    assert runtimes[1].started
    supervisor.close()
    assert supervisor.status().state == "stopped"
    assert runtimes[1].closed


def test_supervisor_rejects_unverified_rotation_and_does_not_start_replacement() -> None:
    runtimes: list[_Runtime] = []

    def factory(previous: BridgeGenerationPair | None):
        runtime = _Runtime(len(runtimes) + 1)
        runtimes.append(runtime)
        return runtime, _generation(len(runtimes))

    supervisor = CompanionBridgeSupervisor(
        runtime_factory=factory,
        authority_receipt_verifier=lambda _digest, _record: False,
        max_restarts=1,
        poll_interval_seconds=0.01,
        backoff_base_seconds=0.01,
    )
    with pytest.raises(CompanionBridgeError, match="authority_receipt_unverified"):
        supervisor.start()
    assert supervisor.status().state == "failed"
    assert runtimes[0].closed
    assert not runtimes[0].started


def test_supervisor_requires_runtime_source_and_acknowledgment_to_match_custody_pair() -> None:
    runtime = _Runtime(1)
    source_generation = _generation(1).source
    wrong_ack_generation = _record("sentientos-core", "core-generation-2",
        "vault://core/key-2", 2, None)
    pair = BridgeGenerationPair(source_generation, wrong_ack_generation)
    supervisor = CompanionBridgeSupervisor(
        runtime_factory=lambda _previous: (runtime, pair),
        authority_receipt_verifier=lambda _digest, _record: True,
    )
    with pytest.raises(CompanionBridgeError, match="runtime_generation_binding_mismatch"):
        supervisor.start()
    assert runtime.closed and not runtime.started


def test_supervisor_recovery_requires_both_source_and_acknowledgment_to_rotate() -> None:
    runtimes: list[_Runtime] = []
    previous_pair = _generation(1)

    def factory(previous: BridgeGenerationPair | None):
        runtime = _Runtime(len(runtimes) + 1)
        runtimes.append(runtime)
        pair = _generation(1) if previous is None else BridgeGenerationPair(
            source=_generation(2).source,
            acknowledgment=previous_pair.acknowledgment,
        )
        return runtime, pair

    supervisor = CompanionBridgeSupervisor(
        runtime_factory=factory,
        authority_receipt_verifier=lambda _digest, _record: True,
        max_restarts=1,
        poll_interval_seconds=0.01,
        backoff_base_seconds=0.01,
    )
    supervisor.start()
    runtimes[0].close()
    deadline = time.monotonic() + 1
    while supervisor.status().state != "failed" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert supervisor.status().state == "failed"
    assert len(runtimes) == 2 and runtimes[1].closed and not runtimes[1].started
    supervisor.close()


def test_supervisor_enforces_bounded_restart_budget_and_closes_failed_listener() -> None:
    runtimes: list[_Runtime] = []

    def factory(previous: BridgeGenerationPair | None):
        number = len(runtimes) + 1
        runtime = _Runtime(number)
        runtimes.append(runtime)
        return runtime, _generation(number)

    supervisor = CompanionBridgeSupervisor(
        runtime_factory=factory,
        authority_receipt_verifier=lambda _digest, _record: True,
        max_restarts=0,
        poll_interval_seconds=0.01,
        backoff_base_seconds=0.01,
    )
    supervisor.start()
    runtimes[0].close()
    deadline = time.monotonic() + 1
    while supervisor.status().state != "failed" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert supervisor.status().state == "failed"
    assert supervisor.status().restart_count == 0
    assert len(runtimes) == 1
    supervisor.close()


def test_supervisor_close_during_recovery_does_not_start_late_runtime() -> None:
    runtimes: list[_Runtime] = []
    factory_entered = threading.Event()
    release_factory = threading.Event()

    def factory(previous: BridgeGenerationPair | None):
        number = len(runtimes) + 1
        if previous is not None:
            factory_entered.set()
            assert release_factory.wait(1)
        runtime = _Runtime(number)
        runtimes.append(runtime)
        return runtime, _generation(number)

    supervisor = CompanionBridgeSupervisor(
        runtime_factory=factory,
        authority_receipt_verifier=lambda _digest, _record: True,
        max_restarts=1,
        poll_interval_seconds=0.01,
        backoff_base_seconds=0.01,
    )
    supervisor.start()
    runtimes[0].close()
    assert factory_entered.wait(1)
    closer = threading.Thread(target=supervisor.close)
    closer.start()
    time.sleep(0.02)
    release_factory.set()
    closer.join(timeout=1)
    assert not closer.is_alive()
    assert supervisor.status().state == "stopped"
    assert len(runtimes) == 2
    assert runtimes[1].closed and not runtimes[1].started
    assert supervisor.generation_id == "generation-1"


def test_foreground_detector_tracks_authorized_generation_after_supervisor_recovery() -> None:
    source_key = b"supervisor-observation-source-key-32-bytes"
    stamp = "2026-11-02T12:00:00+00:00"
    timestamp = datetime.fromisoformat(stamp).timestamp()
    runtimes: list[_Runtime] = []

    def factory(previous: BridgeGenerationPair | None):
        number = len(runtimes) + 1
        runtime = _Runtime(number)
        runtimes.append(runtime)
        return runtime, _generation(number)

    supervisor = CompanionBridgeSupervisor(
        runtime_factory=factory,
        authority_receipt_verifier=lambda _digest, _record: True,
        max_restarts=1,
        poll_interval_seconds=0.01,
        backoff_base_seconds=0.01,
    )
    supervisor.start()
    detector = BridgeForegroundGameDetector(
        runtime=supervisor, source_id="renderer", clock=lambda: datetime.fromisoformat(stamp))

    def verified_observation(number: int):
        receiver = CompanionBridgeReceiver(
            source_keys={"renderer": source_key},
            expected_generations={"renderer": f"generation-{number}"},
            clock=lambda: timestamp,
        )
        encoded = encode_message(
            kind="observation", source_id="renderer", session_id="game-session",
            generation_id=f"generation-{number}", sequence=number,
            payload={
                "schema_version": "sentientos.foreground_game_observation:v1",
                "status": "available", "game_foreground": True,
                "process_name_digest": hashlib.sha256(b"game.exe").hexdigest(),
                "observed_at": stamp,
            }, key=source_key, created_at=stamp,
        )
        return receiver.accept(encoded)

    try:
        runtimes[0].messages.put(verified_observation(1))
        assert detector.observe(("game.exe",)).game_foreground is True
        runtimes[0].close()
        deadline = time.monotonic() + 1
        while supervisor.generation_id != "generation-2" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert supervisor.generation_id == "generation-2"
        runtimes[1].messages.put(verified_observation(2))
        observation = detector.observe(("game.exe",))
        assert observation.game_foreground is True
        assert observation.transport_provenance["generation_id"] == "generation-2"
    finally:
        detector.close()
