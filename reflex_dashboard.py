from logging_config import get_log_path
import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict

import reflex_manager as rm
import reflection_stream as rs
import final_approval

try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - optional
    st = None

from sentient_banner import streamlit_banner, streamlit_closing
import ledger
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()


def load_experiments() -> Dict[str, Any]:
    path = rm.ReflexManager.EXPERIMENTS_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_cli(args: argparse.Namespace) -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    mgr = rm.ReflexManager()
    mgr.load_experiments()

    if args.promote:
        mgr.promote_rule(
            args.promote,
            by=args.agent or "cli",
            persona=args.persona,
            policy=args.policy,
            reviewer=args.reviewer,
        )
    if args.demote:
        mgr.demote_rule(
            args.demote,
            by=args.agent or "cli",
            persona=args.persona,
            policy=args.policy,
            reviewer=args.reviewer,
        )
    if args.freeze:
        mgr.freeze_rule(args.freeze)
    if args.unfreeze:
        mgr.unfreeze_rule(args.unfreeze)
    if args.edit:
        name, key, value = args.edit
        try:
            val = json.loads(value)
        except Exception:
            val = value
        mgr.edit_rule(name, **{key: val})
    if args.revert:
        mgr.revert_last()
    if args.revert_rule:
        mgr.revert_rule(args.revert_rule)
    if args.annotate:
        rule, comment = args.annotate
        tags = [args.tag] if args.tag else None
        mgr.annotate(
            rule,
            comment,
            tags=tags,
            by=args.agent or "cli",
            persona=args.persona,
            policy=args.policy,
            reviewer=args.reviewer,
        )

    if args.list_experiments:
        data = load_experiments()
        for name, info in data.items():
            print(name, info.get("status", "running"))
            for r, stats in info.get("rules", {}).items():
                rate = stats.get("success", 0) / max(1, stats.get("trials", 1))
                print(f"  {r}: {stats.get('trials',0)} trials, {rate:.2f} success")

    if args.log:
        logs = rs.recent_reflex_learn(args.log)
        for l in logs:
            print(json.dumps(l))

    if args.history:
        for entry in mgr.get_history(args.history)[-10:]:
            print(json.dumps(entry))
    if args.audit:
        entries = mgr.get_audit(args.audit)
        if args.filter_agent:
            entries = [e for e in entries if e.get("by") == args.filter_agent]
        if args.filter_persona:
            entries = [e for e in entries if e.get("persona") == args.filter_persona]
        if args.filter_policy:
            entries = [e for e in entries if e.get("policy") == args.filter_policy]
        if args.filter_action:
            entries = [e for e in entries if e.get("action") == args.filter_action]
        for entry in entries:
            print(json.dumps(entry))
    if args.list_feedback:
        path = get_log_path("reflex_user_feedback.jsonl", "FEEDBACK_USER_LOG")
        if path.exists():
            for line in path.read_text().splitlines():
                print(line)
    if args.feedback_log:
        path = get_log_path("reflex_user_feedback.jsonl", "FEEDBACK_USER_LOG")
        if path.exists():
            lines = path.read_text().splitlines()[-args.feedback_log:]
            for ln in lines:
                print(ln)


def run_dashboard() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    if st is None:
        ap = argparse.ArgumentParser(description="Reflex dashboard CLI")
        ap.add_argument("--log", type=int, default=0, help="Show last N learn logs")
        ap.add_argument("--list-experiments", action="store_true")
        ap.add_argument("--promote")
        ap.add_argument("--demote")
        ap.add_argument("--revert", action="store_true")
        ap.add_argument("--revert-rule")
        ap.add_argument("--freeze")
        ap.add_argument("--unfreeze")
        ap.add_argument("--edit", nargs=3, metavar=("RULE", "KEY", "VALUE"))
        ap.add_argument("--history")
        ap.add_argument("--annotate", nargs=2, metavar=("RULE", "COMMENT"))
        ap.add_argument("--tag")
        ap.add_argument("--audit")
        ap.add_argument("--list-feedback", action="store_true")
        ap.add_argument("--feedback-log", type=int)
        ap.add_argument("--agent")
        ap.add_argument("--persona")
        ap.add_argument("--policy")
        ap.add_argument("--reviewer")
        ap.add_argument("--final-approvers", help="Comma or space separated approvers")
        ap.add_argument(
            "--final-approver-file",
            help="File with approver names (JSON list or newline separated)",
        )
        ap.add_argument("--filter-agent")
        ap.add_argument("--filter-persona")
        ap.add_argument("--filter-policy")
        ap.add_argument("--filter-action")
        args = ap.parse_args()
        if args.final_approver_file:
            fp = Path(args.final_approver_file)
            chain = final_approval.load_file_approvers(fp) if fp.exists() else []
            final_approval.override_approvers(chain, source="file")
        elif args.final_approvers:
            fp = Path(args.final_approvers)
            if fp.exists():
                chain = final_approval.load_file_approvers(fp)
            else:
                parts = re.split(r"[,\s]+", args.final_approvers)
                chain = [a.strip() for a in parts if a.strip()]
            final_approval.override_approvers(chain, source="cli")
        run_cli(args)
        return

    st.set_page_config(page_title="Reflex Dashboard")
    st.title("Reflex Experiments")
    streamlit_banner(st)
    ledger.streamlit_widget(st.sidebar if hasattr(st, "sidebar") else st)
    mgr = rm.ReflexManager()
    mgr.load_experiments()
    data = mgr.experiments
    for name, info in data.items():
        st.subheader(name)
        st.write(info.get("status", "running"))
        cols = st.columns(len(info.get("rules", {})))
        for idx, (r, stats) in enumerate(info.get("rules", {}).items()):
            rate = stats.get("success", 0) / max(1, stats.get("trials", 1))
            cols[idx].metric(r, f"{rate:.2f}", f"{stats.get('trials',0)} trials")
        with st.expander("History"):
            for entry in mgr.get_history(name)[-10:]:
                st.json(entry)

    st.header("Recent Learning Events")
    logs = rs.recent_reflex_learn(20)
    for item in logs:
        st.json(item)

    st.header("Audit Log")
    for entry in mgr.get_audit()[-20:]:
        st.json(entry)
    streamlit_closing(st)


if __name__ == "__main__":
    run_dashboard()
