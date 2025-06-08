from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
import streamlit as st

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
# Streamlit dashboard for SentientOS usage and audit metrics.

USAGE_FILE = Path("usage_data.json")
AUDIT_LOG_DIR = Path("audit_logs")
CURRENT_MODEL_FILE = Path("current_model.json")


def load_usage(path: Path) -> pd.DataFrame:
    """Load usage data from a JSONL file into a DataFrame."""
    if not path.exists():
        st.error(f"Usage file not found: {path}")
        return pd.DataFrame()
    try:
        df = pd.read_json(path, lines=True)
    except ValueError as exc:
        st.error(f"Failed to load usage data: {exc}")
        return pd.DataFrame()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def load_audit_summary(directory: Path) -> List[Dict[str, Any]]:
    """Return a summary of audit mismatches per file."""
    summary: List[Dict[str, Any]] = []
    if not directory.exists():
        return summary
    for log_file in directory.glob("*.jsonl"):
        count = 0
        try:
            for line in log_file.read_text(encoding="utf-8").splitlines():
                if "prev hash mismatch" in line:
                    count += 1
        except Exception:
            continue
        summary.append({"file": log_file.name, "mismatches": count})
    return summary


def load_current_model(path: Path) -> Dict[str, Any]:
    """Load the current model selection from JSON."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main() -> None:
    """Render the Streamlit dashboard."""
    st.title("SentientOS Metrics Dashboard")

    usage_df = load_usage(USAGE_FILE)
    audit_summary = load_audit_summary(AUDIT_LOG_DIR)
    current_model = load_current_model(CURRENT_MODEL_FILE)

    st.sidebar.header("Filters")
    if not usage_df.empty:
        min_date = usage_df["timestamp"].min().date()
        max_date = usage_df["timestamp"].max().date()
    else:
        today = date.today()
        min_date = max_date = today
    date_range = st.sidebar.date_input(
        "Date range", (min_date, max_date)
    )
    models = sorted(usage_df["model"].unique().tolist()) if not usage_df.empty else []
    selected_models = st.sidebar.multiselect("Models", models, default=models)

    if not usage_df.empty:
        start, end = date_range[0], date_range[1]
        mask = (
            (usage_df["timestamp"].dt.date >= start)
            & (usage_df["timestamp"].dt.date <= end)
            & (usage_df["model"].isin(selected_models))
        )
        data = usage_df[mask]
        if not data.empty:
            pivot_used = (
                data.pivot(index="timestamp", columns="model", values="messages_used")
                .fillna(method="ffill")
            )
            st.line_chart(pivot_used)

            last = data.sort_values("timestamp").groupby("model").last()
            st.bar_chart(last["messages_remaining"])
        else:
            st.info("No usage data for selected filters.")
    else:
        st.warning("No usage data available.")

    if audit_summary:
        st.subheader("Audit Mismatches")
        st.table(pd.DataFrame(audit_summary))
    else:
        st.info("No audit mismatches found.")

    st.subheader("Current Model Selection")
    if current_model:
        st.json(current_model)
    else:
        st.info("No current model data available.")


if __name__ == "__main__":
    main()
