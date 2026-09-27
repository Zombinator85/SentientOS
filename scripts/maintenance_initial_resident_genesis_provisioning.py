from __future__ import annotations

import argparse
import json

from sentientos import maintenance_initial_resident_genesis_provisioning as genesis


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Compose inert initial resident genesis configuration")
    parser.add_argument("command",choices=("write-template","doctor","render","verify","inspect","print-commissioning-inputs"))
    parser.add_argument("--manifest"); parser.add_argument("--output")
    args=parser.parse_args(argv)
    try:
        if args.command=="write-template":
            if not args.output: parser.error("write-template requires --output")
            result=genesis.write_template(args.output)
        else:
            if not args.manifest: parser.error(args.command+" requires --manifest")
            manifest=genesis.load_manifest(args.manifest)
            result={"doctor":genesis.doctor,"render":genesis.render,"verify":genesis.verify,"inspect":genesis.inspect,"print-commissioning-inputs":genesis.commissioning_inputs}[args.command](manifest)
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        result={"status":"genesis_provisioning_blocked","reason_codes":[str(exc)]}
    print(json.dumps(result,sort_keys=True)); return 2 if result.get("status")=="genesis_provisioning_blocked" else 0


if __name__=="__main__": raise SystemExit(main())
