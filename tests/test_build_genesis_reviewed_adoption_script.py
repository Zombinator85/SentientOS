from __future__ import annotations
import pytest
pytestmark = pytest.mark.no_legacy_skip
import json, subprocess, sys
from pathlib import Path
from tests.test_genesis_reviewed_adoption import packet
from sentientos.genesis_reviewed_adoption import decide, build_plan

def test_cli_decide_validate_plan_and_render(tmp_path: Path):
    pkt=packet(tmp_path); pkt_path=tmp_path/'packet.json'; pkt_path.write_text(json.dumps(pkt.to_dict()), encoding='utf-8')
    dec_path=tmp_path/'decision.json'
    subprocess.run([sys.executable,'scripts/build_genesis_reviewed_adoption.py','decide','--packet',str(pkt_path),'--disposition','approve','--reviewer','operator-1','--reason-code','ok','--output',str(dec_path)], check=True)
    subprocess.run([sys.executable,'scripts/build_genesis_reviewed_adoption.py','validate-decision',str(dec_path),'--packet',str(pkt_path)], check=True)
    plan_path=tmp_path/'plan.json'
    subprocess.run([sys.executable,'scripts/build_genesis_reviewed_adoption.py','plan','--packet',str(pkt_path),'--decision',str(dec_path),'--runtime-root',str(tmp_path/'state'),'--output',str(plan_path)], check=True)
    md=tmp_path/'artifact.md'
    subprocess.run([sys.executable,'scripts/build_genesis_reviewed_adoption.py','render-markdown',str(plan_path),'--output',str(md)], check=True)
    assert 'Genesis reviewed adoption artifact' in md.read_text()
