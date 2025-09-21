def run_once(ledger_queue: Queue) -> dict | None:
    """Execute a single Codex self-repair cycle with multi-iteration and workspace hygiene."""

    passed, summary, _ = run_diagnostics()
    if passed:
        return None

    if CODEX_MODE == "observe":
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt": "",
            "files_changed": [],
            "verified": False,
            "codex_patch": "",
            "iterations": 0,
            "target": CODEX_FOCUS,
            "outcome": "observed",
            "summary": summary,
        }
        log_activity(entry)
        ledger_entry = {
            **entry,
            "event": "codex_observe",
            "codex_mode": CODEX_MODE,
            "ci_passed": False,
        }
        ledger_queue.put(ledger_entry)
        return ledger_entry

    max_iterations = max(1, CODEX_MAX_ITERATIONS)
    current_summary = summary
    cumulative_files: set[str] = set()
    last_entry: dict | None = None

    for iteration in range(1, max_iterations + 1):
        failing_tests = parse_failing_tests(current_summary)
        prompt = (
            "Fix the following issues in SentientOS based on pytest output:\n"
            f"{current_summary}\n"
            "Output a unified diff."
        )
        proc = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True)
        diff_output = proc.stdout

        CODEX_SUGGEST_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        patch_suffix = f"{timestamp}_iter{iteration:02d}"
        patch_path = CODEX_SUGGEST_DIR / f"patch_{patch_suffix}.diff"
        patch_path.write_text(diff_output, encoding="utf-8")

        CODEX_REASONING_DIR.mkdir(parents=True, exist_ok=True)
        trace_path = CODEX_REASONING_DIR / f"trace_{patch_suffix}.json"
        trace_path.write_text(
            json.dumps(
                {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "prompt": prompt,
                    "response": diff_output,
                    "tests_failed": failing_tests,
                    "iteration": iteration,
                    "summary": current_summary,
                }
            ),
            encoding="utf-8",
        )

        files_changed = parse_diff_files(diff_output)
        confirmed = is_safe(files_changed)

        suggestion_entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "self_repair_suggested",
            "tests_failed": failing_tests,
            "patch_file": patch_path.as_posix().lstrip("/"),
            "codex_patch": patch_path.as_posix().lstrip("/"),
            "files_changed": files_changed,
            "confirmed": confirmed,
            "codex_mode": CODEX_MODE,
            "iterations": iteration,
            "iteration": iteration,
            "outcome": "suggested" if confirmed and files_changed else "halted",
            "target": CODEX_FOCUS,
            "verified": False,
            "reasoning_trace": trace_path.as_posix().lstrip("/"),
            "summary": current_summary,
        }
        log_activity({**suggestion_entry, "prompt": prompt})
        ledger_queue.put(suggestion_entry)
        last_entry = suggestion_entry

        if not confirmed or not files_changed:
            suggestion_entry["final_iteration"] = True
            suggestion_entry["max_iterations_reached"] = iteration >= max_iterations
            return suggestion_entry

        # Apply patch with hygiene
        patch_label = patch_path.stem
        patch_result = _call_apply_patch(diff_output, label=patch_label)
        archived_diff = patch_result.get("archived_diff")
        restored_repo = patch_result.get("restored_repo")
        failure_reason = patch_result.get("failure_reason")

        if not patch_result["applied"]:
            fail_entry = {
                **suggestion_entry,
                "event": "self_repair_failed",
                "reason": failure_reason or "patch_apply_failed",
                "failure_reason": failure_reason or "patch_apply_failed",
                "outcome": "fail",
                "restored_repo": bool(restored_repo),
                "archived_diff": archived_diff,
                "final_iteration": True,
                "iterations": iteration,
            }
            log_activity(fail_entry)
            ledger_queue.put(fail_entry)
            return fail_entry

        cumulative_files.update(files_changed)
        tests_passed, new_summary, _ = run_diagnostics()
        if tests_passed:
            subprocess.run(["git", "add", "-A"], check=False)
            subprocess.run(
                ["git", "commit", "-m", "[codex:self_repair] auto-patch applied"],
                check=False,
            )
            success_entry = {
                **suggestion_entry,
                "event": "self_repair",
                "verified": True,
                "outcome": "success",
                "ci_passed": True,
                "files_changed": sorted(cumulative_files),
                "iterations": iteration,
                "final_iteration": True,
                "summary": new_summary,
                "tests_failed": [],
            }
            log_activity(success_entry)
            ledger_queue.put(success_entry)
            send_notifications(success_entry)
            return success_entry

        # Tests still failing → record failure, loop if more iterations allowed
        new_failing_tests = parse_failing_tests(new_summary)
        fail_entry = {
            **suggestion_entry,
            "event": "self_repair_failed",
            "reason": new_summary,
            "failure_reason": "ci_failed",
            "outcome": "fail",
            "tests_failed": new_failing_tests,
            "files_changed": sorted(cumulative_files),
            "iterations": iteration,
            "final_iteration": iteration == max_iterations,
            "max_iterations_reached": iteration >= max_iterations,
            "summary": new_summary,
        }
        log_activity(fail_entry)
        ledger_queue.put(fail_entry)
        last_entry = fail_entry

        if iteration >= max_iterations:
            return fail_entry

        current_summary = new_summary

    return last_entry
