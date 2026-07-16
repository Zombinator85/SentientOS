from pathlib import Path
import pytest

pytestmark = pytest.mark.no_legacy_skip
import json
from scripts.verify_codex_landing_evidence_binding import main

def test_cli_body_and_publication(tmp_path: Path):
    body=tmp_path/'body.md'; body.write_text('### Motivation\n' + 'evidence '*100)
    commit=tmp_path/'commit.json'; commit.write_text(json.dumps({'head_sha':'h','tree_sha':'t','matrix_digest':'m'}))
    art=tmp_path/'art.json'; art.write_text('{}')
    side=tmp_path/'side.json'
    assert main(['bind-body','--title','t','--body-path',str(body),'--commit-binding-json',str(commit),'--artifact',f'a={art}','--output',str(side)]) == 0
    assert main(['verify-body','--title','t','--body-path',str(body),'--binding-json',str(side),'--artifact',f'a={art}','--summary']) == 0
    pub=tmp_path/'pub.json'; exp=tmp_path/'exp.json'; pub.write_text(json.dumps({'title':'t','body':'b'})); exp.write_text(json.dumps({'title':'t'}))
    assert main(['classify-publication','--publication-json',str(pub),'--expected-json',str(exp),'--summary']) == 0
