"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import argparse
import json
import experiment_tracker as et
from sentientos.experiments import hypothesis
from sentientos.experiments.chain import (
    ChainStep,
    ExperimentChain,
    list_chains as list_saved_chains,
    load_chain,
    save_chain,
)
from sentientos.experiments.runner import run_chain
from sentient_banner import print_banner, print_closing, ENTRY_BANNER

def main() -> None:
    parser = argparse.ArgumentParser(description=ENTRY_BANNER)
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("propose")
    p.add_argument("description")
    p.add_argument("conditions")
    p.add_argument("expected")
    p.add_argument("--criteria")
    p.add_argument("--user")
    p.add_argument("--requires-consensus", action="store_true")
    p.add_argument("--quorum-k", type=int)
    p.add_argument("--quorum-n", type=int)

    l = sub.add_parser("list")
    l.add_argument("--status")

    v = sub.add_parser("vote")
    v.add_argument("id")
    v.add_argument("direction", choices=["up", "down"])
    v.add_argument("--user", required=True)

    sg = sub.add_parser("suggest")
    sg.add_argument("--event", required=True, help="JSON description of the triggering event")

    c = sub.add_parser("comment")
    c.add_argument("id")
    c.add_argument("text")
    c.add_argument("--user", required=True)

    s = sub.add_parser("set-status")
    s.add_argument("id")
    s.add_argument("status")

    e = sub.add_parser("eval-criteria")
    e.add_argument("id")
    e.add_argument("context")

    cn = sub.add_parser("chain-new")
    cn.add_argument("chain_id")
    cn.add_argument("sequence")
    cn.add_argument("--description", default="")
    cn.add_argument("--max-steps", type=int, default=32)

    cr = sub.add_parser("chain-run")
    cr.add_argument("chain_id")

    cl = sub.add_parser("chain-list")

    args = parser.parse_args()
    print_banner()

    if args.cmd == "propose":
        eid = et.propose_experiment(
            args.description,
            args.conditions,
            args.expected,
            proposer=args.user,
            criteria=args.criteria,
            requires_consensus=args.requires_consensus,
            quorum_k=args.quorum_k,
            quorum_n=args.quorum_n,
        )
        print(eid)
    elif args.cmd == "list":
        for info in et.list_experiments(args.status):
            rate = info.get("success", 0) / max(1, info.get("triggers", 1))
            dsl_marker = " [DSL]" if info.get("criteria") else ""
            consensus_marker = ""
            vote_marker = ""
            if info.get("requires_consensus"):
                consensus_marker = " [CONSENSUS]"
                votes = info.get("votes") or {}
                approvals = sum(1 for v in votes.values() if v in {"up", True, 1})
                target = info.get("quorum_n") or info.get("quorum_k") or 0
                target = max(int(target or 0), 1)
                vote_marker = f" ({approvals}/{target} votes)"
            print(
                info["id"],
                info.get("status"),
                f"{rate:.2f}",
                f"{info.get('description', '')}{dsl_marker}{consensus_marker}{vote_marker}",
            )
    elif args.cmd == "vote":
        upvote = args.direction == "up"
        recorded = et.vote_experiment(args.id, args.user, upvote=upvote)
        if not recorded:
            print("Vote rejected or duplicate; no changes recorded.")
        info = et.get_experiment(args.id)
        if info:
            status = info.get("status")
            if status in {"active", "rejected", "digest_mismatch"}:
                print(f"Experiment {args.id} is now {status}.")
    elif args.cmd == "comment":
        et.comment_experiment(args.id, args.user, args.text)
    elif args.cmd == "suggest":
        try:
            event = json.loads(args.event)
            if not isinstance(event, dict):
                raise ValueError("Event must be a JSON object")
        except Exception as exc:
            print(f"Invalid event JSON: {exc}")
        else:
            spec = hypothesis.generate_hypothesis(event)
            if spec:
                print(json.dumps(spec, indent=2, sort_keys=True))
            else:
                print("No hypothesis generated (rate limited or filtered).")
    elif args.cmd == "set-status":
        et.update_status(args.id, args.status)
    elif args.cmd == "eval-criteria":
        try:
            context = json.loads(args.context)
            if not isinstance(context, dict):
                raise ValueError("Context JSON must describe an object")
        except Exception as exc:
            print(f"Invalid context: {exc}")
        else:
            result = et.evaluate_and_log_experiment_success(args.id, context)
            print("PASS" if result else "FAIL")
    elif args.cmd == "chain-new":
        step_ids = [segment.strip() for segment in args.sequence.split(",") if segment.strip()]
        if not step_ids:
            print("Chain sequence must include at least one experiment id.")
        else:
            steps = {}
            for idx, step_id in enumerate(step_ids):
                next_id = step_ids[idx + 1] if idx + 1 < len(step_ids) else None
                steps[step_id] = ChainStep(id=step_id, on_success=next_id, on_failure=None)
            try:
                chain = ExperimentChain(
                    chain_id=args.chain_id,
                    description=args.description,
                    start=step_ids[0],
                    steps=steps,
                    max_steps=args.max_steps,
                )
            except ValueError as exc:
                print(f"Failed to create chain: {exc}")
            else:
                save_chain(chain)
                print(f"Chain '{args.chain_id}' saved with {len(step_ids)} steps.")
    elif args.cmd == "chain-run":
        chain = load_chain(args.chain_id)
        if not chain:
            print(f"Chain '{args.chain_id}' not found.")
        else:
            def _progress(step_result):
                step = chain.steps.get(step_result.experiment_id)
                if step_result.success is True:
                    status = "SUCCESS"
                    next_step = step.on_success if step else None
                elif step_result.success is False:
                    status = "FAILURE"
                    next_step = step.on_failure if step else None
                else:
                    status = step_result.error or "SKIPPED"
                    next_step = None

                if next_step:
                    print(
                        f"[chain {chain.chain_id}] step {step_result.step_index}: "
                        f"{step_result.experiment_id} → {status} → next {next_step}"
                    )
                else:
                    print(
                        f"[chain {chain.chain_id}] step {step_result.step_index}: "
                        f"{step_result.experiment_id} → {status} → chain complete"
                    )

            result = run_chain(chain, progress_callback=_progress)
            print(f"[chain {chain.chain_id}] outcome: {result.outcome}")
    elif args.cmd == "chain-list":
        chains = list(list_saved_chains())
        if not chains:
            print("No chains defined.")
        for chain in chains:
            print(
                f"{chain.chain_id}\t{chain.description}\tstart={chain.start}\tsteps={len(chain.steps)}"
            )
    else:
        parser.print_help()
    print_closing()


if __name__ == "__main__":
    main()
