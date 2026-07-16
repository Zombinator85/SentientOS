import pytest
from sentientos.world_state_sources import SourceDeclaration, load_manifest, WorldStateSourceManifestError

def test_manifest_bounds_path_safety_and_dedup(tmp_path):
    good=tmp_path/'good.json'; good.write_text('{"subject_id":"a"}')
    rows=load_manifest([SourceDeclaration('s','capability_registry',path=good), SourceDeclaration('s','capability_registry',path=good)], allowed_roots=[tmp_path])
    assert len(rows)==1
    with pytest.raises(WorldStateSourceManifestError): load_manifest([SourceDeclaration(str(i),'capability_registry',record={}) for i in range(3)], allowed_roots=[tmp_path], max_source_count=2)
    with pytest.raises(WorldStateSourceManifestError): load_manifest([SourceDeclaration('bad','capability_registry',path=tmp_path/'..'/'x')], allowed_roots=[tmp_path])

def test_manifest_malformed_unsupported_oversized_digest(tmp_path):
    bad=tmp_path/'bad.json'; bad.write_text('{')
    with pytest.raises(WorldStateSourceManifestError): load_manifest([SourceDeclaration('b','capability_registry',path=bad)], allowed_roots=[tmp_path])
    with pytest.raises(WorldStateSourceManifestError): load_manifest([SourceDeclaration('u','unknown',record={})], allowed_roots=[tmp_path])
    big=tmp_path/'big.json'; big.write_text('{"x":"abcdef"}')
    with pytest.raises(WorldStateSourceManifestError): load_manifest([SourceDeclaration('big','capability_registry',path=big)], allowed_roots=[tmp_path], max_artifact_size=3)
    rows=load_manifest([SourceDeclaration('d','capability_registry',record={},digest='wrong')], allowed_roots=[tmp_path])
    assert rows[0]['digest']=='wrong'
