import json, subprocess, sys

def test_world_state_cli_build_and_views(tmp_path):
    inp=tmp_path/'in.json'; inp.write_text(json.dumps([{"source_kind":"capability_registry","source_id":"c","subject_id":"c"}]))
    out=subprocess.check_output([sys.executable,'scripts/build_world_state_board.py','summarize','--input',str(inp)], text=True)
    assert 'source_kind' in out
    md=subprocess.check_output([sys.executable,'scripts/build_world_state_board.py','render-markdown','--input',str(inp)], text=True)
    assert 'Authority: view-only' in md
