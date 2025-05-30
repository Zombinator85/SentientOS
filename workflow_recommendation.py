import datetime
from typing import Any, Dict, List

import workflow_library as wl
import workflow_analytics as wa
import reflection_stream as rs


def recommend_workflows(analytics_data: Dict[str, Any]) -> List[str]:
    suggestions: List[str] = []
    usage = analytics_data.get("usage", {})
    trends = analytics_data.get("trends", {})
    now = datetime.datetime.utcnow()
    for wf, info in usage.items():
        if info.get("fail_rate", 0) > 0.5:
            suggestions.append(f"Review failing workflow '{wf}'")
        last = info.get("last_ts")
        if last:
            try:
                dt = datetime.datetime.fromisoformat(last)
            except Exception:
                dt = now
            if (now - dt).days > 7:
                suggestions.append(f"Workflow '{wf}' hasn't run recently")
    for wf in wl.list_templates():
        if wf not in usage:
            suggestions.append(f"Consider trying workflow '{wf}'")
    for wf in wl.list_templates():
        path = wl.get_template_path(wf)
        if path:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            steps = text.count("action")
            if steps > 8:
                suggestions.append(f"Split long workflow '{wf}' into smaller parts")
                break
    for rec in suggestions:
        try:
            rs.log_event("workflow", "recommend", "analytics", "suggest", {"text": rec})
        except Exception:
            pass
    return suggestions


def main() -> None:  # pragma: no cover - CLI
    import argparse
    parser = argparse.ArgumentParser(description="Workflow recommendations")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    data = wa.analytics(args.limit)
    for rec in recommend_workflows(data):
        print(f"- {rec}")


if __name__ == "__main__":
    main()
