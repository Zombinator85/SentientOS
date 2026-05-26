from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path
from sentientos.codex_strict_audit_repair import CodexStrictAuditRepairRequest, diagnose_strict_audit_repair

def _run(cmd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd.split(), check=False, capture_output=True, text=True)

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("mode", choices=("diagnose","repair","summarize"))
    p.add_argument("--strict-output")
    p.add_argument("--audit-path", default="pulse/audit/privileged_audit.runtime.jsonl")
    p.add_argument("--allow-runtime-chain-reseal", action="store_true")
    p.add_argument("--output")
    p.add_argument("--summary", action="store_true")
    a=p.parse_args(argv)
    if a.strict_output:
      text=Path(a.strict_output).read_text(encoding="utf-8"); code=1
    else:
      cp=_run("python verify_audits.py --strict"); text=(cp.stdout or "")+"\n"+(cp.stderr or ""); code=cp.returncode
    result=diagnose_strict_audit_repair(CodexStrictAuditRepairRequest(text, code, a.audit_path))
    payload=result.to_dict()
    if a.mode=="repair":
      status=payload["report"]["finding"]["status"]
      if status=="audit_repair_ready" and not a.allow_runtime_chain_reseal:
        print(json.dumps(payload, indent=2, sort_keys=True)); return 2
      if status=="audit_repair_ready":
        changed_before=set(Path('.').glob('**/*'))
        for cmd in payload["report"]["action"]["commands"]:
          cp=_run(cmd)
          if cp.returncode!=0: return 3
        changed_after=set(Path('.').glob('**/*'))
        payload["report"]["changed_files"]=tuple(sorted(str(p) for p in changed_after-changed_before))
        payload["report"]["finding"]["status"]="audit_repair_applied"
      elif status!="audit_repair_not_needed":
        print(json.dumps(payload, indent=2, sort_keys=True)); return 4
    if a.output: Path(a.output).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    if a.summary:
      print(json.dumps({"status": payload["report"]["finding"]["status"], "classification": payload["report"]["finding"]["classification"]}, indent=2))
    else: print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
