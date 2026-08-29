from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from sentientos.codex_landing_evidence_binding import classify_publication_result, create_body_binding, create_pr_publication_handoff, verify_body_binding, verify_pr_publication_handoff

from typing import Any

def load(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('JSON artifact must be an object')
    return data

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd', required=True)
    b=sub.add_parser('bind-body'); b.add_argument('--title', required=True); b.add_argument('--body-path', required=True); b.add_argument('--commit-binding-json', required=True); b.add_argument('--artifact', action='append', default=[]); b.add_argument('--output', required=True)
    v=sub.add_parser('verify-body'); v.add_argument('--title', required=True); v.add_argument('--body-path', required=True); v.add_argument('--binding-json', required=True); v.add_argument('--artifact', action='append', default=[]); v.add_argument('--summary', action='store_true')
    c=sub.add_parser('classify-publication'); c.add_argument('--publication-json', required=True); c.add_argument('--expected-json', required=True); c.add_argument('--summary', action='store_true')
    for name in ('seal-publication-handoff', 'verify-publication-handoff'):
        h=sub.add_parser(name); h.add_argument('--repository', required=True); h.add_argument('--intended-base-ref', required=True); h.add_argument('--body-path', required=True); h.add_argument('--body-binding-json', required=True); h.add_argument('--pre-commit-finalizer-json', required=True); h.add_argument('--pr-metadata-finalizer-json', required=True); h.add_argument('--pr-metadata-guard-json', required=True); h.add_argument('--handoff-json', required=name.startswith('verify')); h.add_argument('--output', required=name.startswith('seal')); h.add_argument('--summary', action='store_true')
    a=p.parse_args(argv)
    def artifacts(items: list[str]) -> dict[str, str]:
        return dict(item.split('=',1) for item in items)
    if a.cmd=='bind-body':
        side=create_body_binding(a.title, a.body_path, load(a.commit_binding_json), artifacts(a.artifact)).to_dict(); Path(a.output).write_text(json.dumps(side, indent=2, sort_keys=True), encoding='utf-8'); print(json.dumps({'status':'pr_body_binding_written','body_sha256':side['body_sha256']}, indent=2)); return 0
    if a.cmd=='verify-body':
        res=verify_body_binding(a.title, a.body_path, load(a.binding_json), artifacts(a.artifact)); print(json.dumps(res.to_dict() if not a.summary else {'status':res.status,'reasons':res.reasons,'proof':res.proof}, indent=2, sort_keys=True)); return 0 if res.status=='pr_body_binding_ready' else 1
    if a.cmd in ('seal-publication-handoff', 'verify-publication-handoff'):
        inputs={'repository':a.repository,'intended_base_ref':a.intended_base_ref,'body_path':a.body_path,'body_binding_path':a.body_binding_json,'pre_commit_finalizer_path':a.pre_commit_finalizer_json,'pr_metadata_finalizer_path':a.pr_metadata_finalizer_json,'pr_metadata_guard_path':a.pr_metadata_guard_json}
        if a.cmd=='seal-publication-handoff':
            handoff=create_pr_publication_handoff(**inputs).to_dict(); rendered=json.dumps(handoff, indent=2, sort_keys=True)+'\n'; output=Path(a.output)
            if output.exists() and output.read_bytes() != rendered.encode('utf-8'): raise ValueError('publication_handoff_output_collision')
            if not output.exists():
                output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(rendered.encode('utf-8'))
            print(json.dumps({'status':handoff['status'],'handoff_sha256':handoff['handoff_sha256'],'body_sha256':handoff['body_sha256'],'body_byte_length':handoff['body_byte_length']}, indent=2, sort_keys=True)); return 0
        res=verify_pr_publication_handoff(load(a.handoff_json), **inputs); print(json.dumps(res.to_dict(), indent=2, sort_keys=True)); return 0 if res.status=='pr_publication_handoff_ready' else 1
    res=classify_publication_result(load(a.publication_json), load(a.expected_json)); print(json.dumps(res.to_dict() if not a.summary else {'status':res.status,'reasons':res.reasons,'proof':res.proof}, indent=2, sort_keys=True)); return 0 if not res.status.endswith('contradicted') else 1
if __name__=='__main__': raise SystemExit(main())
