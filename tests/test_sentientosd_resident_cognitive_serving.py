from pathlib import Path
import pytest
import sentientosd
pytestmark=pytest.mark.no_legacy_skip

def test_explicit_resident_invoker_is_independent(monkeypatch,tmp_path):
    config=tmp_path/"resident.json"; config.write_text('{"schema":"sentientos.resident_developmental_cognition_config:v1","history_root":"'+str(tmp_path/'history')+'","state_root":"'+str(tmp_path/'state')+'","allowed_source_kinds":["test"],"max_selected_facts":1,"max_retrieved_records":1,"comparison_enabled":false,"enabled":true}')
    monkeypatch.setenv(sentientosd.RESIDENT_DEVELOPMENTAL_CONFIG_ENV,str(config))
    general=object(); resident=object()
    surfaces=sentientosd.RuntimeMaintenanceSurfaces(Path.cwd(),governed_local_invoker=general,resident_cognitive_invoker=resident)
    assert surfaces._resident_developmental_owner is not None
    assert surfaces._resident_developmental_owner.invoker is resident
    assert surfaces._governed_local_invoker is general

def test_enabled_failure_never_substitutes_legacy_invoker(monkeypatch,tmp_path):
    config=tmp_path/"resident.json"; config.write_text('{"schema":"sentientos.resident_developmental_cognition_config:v1","history_root":"'+str(tmp_path/'history')+'","state_root":"'+str(tmp_path/'state')+'","allowed_source_kinds":["test"],"max_selected_facts":1,"max_retrieved_records":1,"comparison_enabled":false,"enabled":true}')
    monkeypatch.setenv(sentientosd.RESIDENT_DEVELOPMENTAL_CONFIG_ENV,str(config))
    surfaces=sentientosd.RuntimeMaintenanceSurfaces(Path.cwd(),governed_local_invoker=None,genesis_advice_source=object())
    assert surfaces._resident_developmental_owner is None
    assert surfaces._resident_developmental_configuration_error=="governed_local_invoker_unavailable"
    assert surfaces._genesis_advice_source is not None
