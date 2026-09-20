from pathlib import Path
import pytest
from sentientos.codex_task_authority_admission import EXTERNAL_MODEL_INFERENCE_DEFINITION, authority_definition_digest
from sentientos.cognition import GoalSelectionKernel, run_cognitive_cycle
from sentientos.consciousness.integration import run_consciousness_cycle
from sentientos.consciousness.sentience_kernel import SentienceKernel
from sentientos.public_language_map import CONTEXT_SENSITIVE_TERMS, PUBLIC_LANGUAGE_MAP
ROOT=Path(__file__).parents[1]; pytestmark=pytest.mark.no_legacy_skip
def test_public_language_map_is_consistent_and_contextual_terms_are_not_global_mappings():
 assert CONTEXT_SENSITIVE_TERMS.isdisjoint(PUBLIC_LANGUAGE_MAP)
 assert all(k==v.legacy_term and v.normalized_term and v.rationale for k,v in PUBLIC_LANGUAGE_MAP.items())
 assert {"council","presence","self-model","trust","oracle","witness","healing"} <= CONTEXT_SENSITIVE_TERMS
def test_canonical_cognition_api_and_legacy_aliases_have_behavior_parity():
 assert SentienceKernel is GoalSelectionKernel
 assert run_consciousness_cycle({"posture_history":[]}) == run_cognitive_cycle({"posture_history":[]})
def test_obsolete_cultural_artifacts_are_not_retained_as_an_archive():
 removed=("bootstrap_blessing.md","BLESSED_FEDERATION_LAUNCH.md","docs/CATHEDRAL_MEMORY_MANIFESTO.md","docs/CATHEDRAL_HEALING_SPRINT.md","docs/MEMORY_HEALING_RITUAL.md","docs/WHY_JOIN_AUDIT_SAINTS.md",".github/ISSUE_TEMPLATE/share_your_saint_story.yml")
 assert all(not (ROOT/p).exists() for p in removed)
def test_external_model_authority_definition_is_unchanged():
 assert authority_definition_digest(EXTERNAL_MODEL_INFERENCE_DEFINITION)=="539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c"
