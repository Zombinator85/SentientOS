from pathlib import Path

import pytest

from sentientos.developmental_model_replacement_experimental_serving import ACTION, PRINCIPAL, TARGET_SUBSYSTEM
from sentientos.governed_local_model_invocation import MODEL_REPLACEMENT_PURPOSE, SUPPORTED_PURPOSES

pytestmark = pytest.mark.no_legacy_skip


def test_model_serving_admission_precedes_construction() -> None:
    source = Path("sentientos/developmental_model_replacement_experimental_serving.py").read_text()
    assert source.index("self._kernel.admit") < source.index("self._factory(chain")
    assert (ACTION, PRINCIPAL, TARGET_SUBSYSTEM) == ("load_preregistered_experimental_local_model",
        "deterministic_developmental_model_replacement_experimental_serving_controller", "local_model_chat")


def test_exact_loaded_identity_required_and_failure_cleanup() -> None:
    source = Path("sentientos/developmental_model_replacement_experimental_serving.py").read_text()
    assert "if loaded != expected" in source
    assert "worker.close()" in source


def test_separate_inference_admission_and_temperature_zero() -> None:
    source = Path("sentientos/governed_local_model_invocation.py").read_text()
    endpoint = Path("sentientos/developmental_model_replacement_experimental_serving.py").read_text()
    assert MODEL_REPLACEMENT_PURPOSE in SUPPORTED_PURPOSES
    assert "MODEL_REPLACEMENT_PURPOSE} else None" in source
    assert "AuthorityClass.MODEL_SERVING" in endpoint and "GovernedLocalModelInvoker" in endpoint
    assert "inference_admission_not_independent" in endpoint


def test_canonical_activation_and_serving_preservation() -> None:
    source = Path("sentientos/developmental_model_replacement_experimental_serving.py").read_text()
    assert "local-model/activation" not in source
    assert '"local-model/serving' not in source
    assert '"canonical_activation_mutated": False' in source
    assert '"canonical_production_serving_mutated": False' in source


def test_deterministic_bounded_unload_and_double_close() -> None:
    source = Path("sentientos/developmental_model_replacement_experimental_serving.py").read_text()
    assert "if self._closed: return" in source
    assert '"bounded_unload_performed": True' in source


def test_serving_transition_performs_zero_inference() -> None:
    source = Path("sentientos/developmental_model_replacement_experimental_serving.py").read_text()
    establish = source[source.index("    def establish"):source.index("class ExperimentalCognitiveEndpoint")]
    assert ".generate(" not in establish and ".invoke(" not in establish
    assert '"inference_performed_by_serving_transition": False' in establish
