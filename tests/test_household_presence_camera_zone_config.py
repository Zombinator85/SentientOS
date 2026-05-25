import json
from pathlib import Path
from sentientos.household_presence_camera_zone_config import build_default_config, validate_zone_config, to_deadzone_redaction_regions

FX=Path('tests/fixtures/household_presence_camera_zone_configs')

def _f(n): return json.loads((FX/n).read_text())

def test_default_config_validates():
    assert validate_zone_config({'zones':build_default_config()}).report.status=='valid'

def test_fixtures_metadata_only_and_rules():
    for p in FX.glob('*.json'):
        t=p.read_text().lower()
        assert 'base64' not in t and 'image' not in t and 'audio' not in t

def test_specific_fixtures_behaviors():
    assert validate_zone_config({'zones':_f('invalid_speaker_output_config.json')}).report.status=='blocked'
    assert validate_zone_config({'zones':_f('invalid_external_disclosure_config.json')}).report.status=='blocked'
    assert validate_zone_config({'zones':_f('stale_config_requires_review.json')}).report.status=='review_required'
    r=validate_zone_config({'zones':_f('mixed_overlap_precedence_config.json')})
    assert r.normalized_config[0].zone_class=='deadzone'

def test_compat_helper_regions():
    r=validate_zone_config({'zones':_f('exterior_camera_deadzone_window_mask_config.json')})
    assert to_deadzone_redaction_regions(r)[0]['zone_classification']=='deadzone'
