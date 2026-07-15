from __future__ import annotations
# mypy: disable-error-code="no-untyped-def,no-untyped-call"

import argparse, json, sys
from pathlib import Path

from sentientos.genesis_model_advice import GenesisModelAdviceRequestContext, GenesisModelAdvicePacket, build_prompt, parse_advice_output, validate_packet
from sentientos.local_model_authority import atomic_write_json

MALFORMED=2; INVALID_OUTPUT=4; INVALID_SAVED=6

def _load(path: str):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def _dump(obj, path: str|None):
    text=json.dumps(obj, indent=2, sort_keys=True)+"\n"
    if path: atomic_write_json(Path(path), obj)
    else: print(text, end='')

def cmd_build_request(args):
    ctx=GenesisModelAdviceRequestContext(need_identity=args.need_identity, capability=args.capability, source_kind=args.source_kind, need_description=args.need_description, signal_batch_id=args.signal_batch_id, signal_batch_digest=args.signal_batch_digest, authority_map_id=args.authority_map_id, authority_map_digest=args.authority_map_digest, model_id=args.model_id, model_artifact_digest=args.model_artifact_digest, correlation_id=args.correlation_id or f"cli:{args.need_identity}")
    payload={**ctx.semantic_payload(), "request_id":ctx.request_id, "request_digest":ctx.request_digest, "prompt_preview": build_prompt(ctx)}
    _dump(payload,args.output); return 0

def cmd_validate_request(args):
    data=_load(args.path); required={"request_id","request_digest","need_identity","signal_batch_digest","proposal_only"}
    missing=sorted(required-set(data))
    if missing: print("missing:"+",".join(missing), file=sys.stderr); return MALFORMED
    return 0

def cmd_validate_advice_output(args):
    payload,reasons=parse_advice_output(Path(args.path).read_text(encoding='utf-8'))
    if reasons: print(json.dumps({"valid":False,"reasons":reasons},sort_keys=True)); return INVALID_OUTPUT
    print(json.dumps({"valid":True,"payload":payload.to_dict() if payload else None},sort_keys=True)); return 0

def cmd_build_packet(args):
    req=_load(args.request); rec=_load(args.receipt); text=Path(args.output_text).read_text(encoding='utf-8')
    payload,reasons=parse_advice_output(text)
    norm=payload.to_dict() if payload else None
    pkt=GenesisModelAdvicePacket(request_context=req, invocation_receipt=rec, normalized_output=norm, disposition="valid_advice" if payload else "invalid_or_denied", validation_findings=tuple(reasons), fallback_posture="none" if payload else "deterministic_fallback", candidate_produced=payload is not None)
    _dump(pkt.to_dict(), args.output); return 0 if payload else INVALID_OUTPUT

def cmd_validate_packet(args):
    ok,reasons=validate_packet(_load(args.path)); print(json.dumps({"valid":ok,"reasons":reasons},sort_keys=True)); return 0 if ok else INVALID_SAVED

def cmd_preview_candidate(args):
    pkt=_load(args.packet); ok,reasons=validate_packet(pkt)
    if not ok: print(json.dumps({"valid":False,"reasons":reasons},sort_keys=True)); return INVALID_SAVED
    out={"candidate_origin":"governed_local_model_advice","packet_id":pkt["packet_id"],"proposal_only":True,"forbidden_effects":pkt.get("effects",{})}
    _dump(out,args.output); return 0

def cmd_summarize(args):
    data=_load(args.path); out={"schema_version":data.get("schema_version"),"id":data.get("packet_id") or data.get("request_id"),"digest":data.get("packet_digest") or data.get("request_digest"),"disposition":data.get("disposition")}
    if args.markdown: print("# Genesis Model Advice Summary\n\n"+"\n".join(f"- **{k}**: `{v}`" for k,v in out.items())+"\n")
    else: _dump(out,args.output)
    return 0

def main(argv=None):
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(required=True)
    p=sub.add_parser('build-request');
    for name in ['need-identity','capability','source-kind','need-description','signal-batch-id','signal-batch-digest','authority-map-id','authority-map-digest','model-id']:
        p.add_argument('--'+name, required=True)
    p.add_argument('--model-artifact-digest'); p.add_argument('--correlation-id'); p.add_argument('--output'); p.set_defaults(func=cmd_build_request)
    p=sub.add_parser('validate-request'); p.add_argument('path'); p.set_defaults(func=cmd_validate_request)
    p=sub.add_parser('validate-advice-output'); p.add_argument('path'); p.set_defaults(func=cmd_validate_advice_output)
    p=sub.add_parser('build-packet'); p.add_argument('--request',required=True); p.add_argument('--receipt',required=True); p.add_argument('--output-text',required=True); p.add_argument('--output'); p.set_defaults(func=cmd_build_packet)
    p=sub.add_parser('validate-packet'); p.add_argument('path'); p.set_defaults(func=cmd_validate_packet)
    p=sub.add_parser('preview-candidate'); p.add_argument('packet'); p.add_argument('--output'); p.set_defaults(func=cmd_preview_candidate)
    p=sub.add_parser('summarize'); p.add_argument('path'); p.add_argument('--markdown',action='store_true'); p.add_argument('--output'); p.set_defaults(func=cmd_summarize)
    args=ap.parse_args(argv); return args.func(args)
if __name__=='__main__': raise SystemExit(main())
