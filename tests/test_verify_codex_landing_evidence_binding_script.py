from pathlib import Path
import pytest

pytestmark = pytest.mark.no_legacy_skip
import json
from scripts.verify_codex_landing_evidence_binding import main
from tests.test_codex_landing_evidence_binding import publication_inputs

def test_cli_body_and_publication(tmp_path: Path):
    body=tmp_path/'body.md'; body.write_text('### Motivation\n' + 'evidence '*100)
    commit=tmp_path/'commit.json'; commit.write_text(json.dumps({'head_sha':'h','tree_sha':'t','matrix_digest':'m'}))
    art=tmp_path/'art.json'; art.write_text('{}')
    side=tmp_path/'side.json'
    assert main(['bind-body','--title','t','--body-path',str(body),'--commit-binding-json',str(commit),'--artifact',f'a={art}','--output',str(side)]) == 0
    assert main(['verify-body','--title','t','--body-path',str(body),'--binding-json',str(side),'--artifact',f'a={art}','--summary']) == 0
    pub=tmp_path/'pub.json'; exp=tmp_path/'exp.json'; pub.write_text(json.dumps({'title':'t','body':'b'})); exp.write_text(json.dumps({'title':'t'}))
    assert main(['classify-publication','--publication-json',str(pub),'--expected-json',str(exp),'--summary']) == 0

def test_cli_seals_and_verifies_publication_handoff_without_publication(tmp_path: Path):
    inputs, paths=publication_inputs(tmp_path); output=tmp_path/'handoff.json'
    common=['--repository',str(inputs['repository']),'--intended-base-ref',str(inputs['intended_base_ref']),'--body-path',str(paths['body']),'--body-binding-json',str(paths['binding']),'--pre-commit-finalizer-json',str(paths['pre']),'--pr-metadata-finalizer-json',str(paths['post']),'--pr-metadata-guard-json',str(paths['guard'])]
    assert main(['seal-publication-handoff',*common,'--output',str(output),'--summary']) == 0
    assert json.loads(output.read_text())['status']=='pr_publication_handoff_ready'
    assert main(['verify-publication-handoff',*common,'--handoff-json',str(output),'--summary']) == 0
