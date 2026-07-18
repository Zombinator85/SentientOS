#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.host_fulfillment_authorization_runtime import HostFulfillmentAuthorizationRuntimeCoordinator

def main() -> int:
    parser=argparse.ArgumentParser(description='Build metadata-only host fulfillment authorization consumption custody artifacts.')
    parser.add_argument('--runtime-state-root', default=None)
    parser.add_argument('--summary-output', default=None)
    parser.add_argument('--demo', action='store_true', help='Only report runtime posture; does not consume or fulfill.')
    args=parser.parse_args()
    coord=HostFulfillmentAuthorizationRuntimeCoordinator(runtime_state_root=args.runtime_state_root)
    payload={'status':'ready','metadata_only':True,'consumption_call_count':0,'admission_call_count':coord.admission_call_count,'fulfillment_granted':False,'executor_authorized':False,'backend_invoked':False,'execution_triggered':False,'host_mutation_performed':False}
    if args.summary_output:
        Path(args.summary_output).write_text(json.dumps(payload,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps(payload,sort_keys=True))
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
