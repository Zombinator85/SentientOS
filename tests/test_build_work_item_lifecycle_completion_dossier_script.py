import json
import subprocess


def test_script_summary(tmp_path):
    c = tmp_path/"c.json"; p = tmp_path/"p.json"; o = tmp_path/"o.json"
    c.write_text(json.dumps({"status":"lifecycle_closure_run_completed","packet":{"work_item_id":"w1","lifecycle_closure_wing_invoked":True,"lifecycle_closure_run_packet_id":"c1","lifecycle_closure_run_packet_digest":"d1"}}))
    p.write_text(json.dumps({"work_item_id":"w1"}))
    run = subprocess.run(["python","scripts/build_work_item_lifecycle_completion_dossier.py","--closure-run",str(c),"--proposal",str(p),"--output",str(o),"--summary"], text=True, capture_output=True, check=False)
    assert run.returncode == 0
    assert "status=" in run.stdout
    assert o.exists()
