from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Callable, Iterable, Literal, Mapping, Sequence

from control_plane.records import AuthorizationRecord
import task_executor


BundleClassification = Literal["completed", "refused", "blocked", "exhausted", "failed", "unknown_prerequisite"]


@dataclass(frozen=True)
class BundledTask:
    task: task_executor.Task
    bundle_id: str
    intent: str
    identity_digest: str


@dataclass(frozen=True)
class ApprovalAction:
    task_id: str
    action_id: str
    description: str
    authority_impact: task_executor.EprAuthorityImpact
    reversibility: task_executor.EprReversibility
    rollback_proof: task_executor.EprRollbackProof


@dataclass(frozen=True)
class ApprovalRequest:
    bundle_id: str
    intent: str
    identity_digest: str
    actions: Sequence[ApprovalAction]


@dataclass(frozen=True)
class ApprovalSummary:
    requested: bool
    granted: bool | None
    prompt_count: int
    actions: Sequence[ApprovalAction]


@dataclass(frozen=True)
class TaskOutcome:
    task_id: str
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class BundleExecutionReport:
    classification: BundleClassification
    intent: str
    bundle_id: str
    identity_digest: str
    approval: ApprovalSummary
    tasks: Sequence[TaskOutcome]
    automatic_repairs: Sequence[str]
    authority_used: Sequence[str]
    skipped: Sequence[str]
    blocked: Sequence[str]
    stop_reason: str | None = None

    def render_summary(self) -> str:
        approvals = "yes" if self.approval.requested else "no"
        approval_granted = (
            "yes" if self.approval.granted else "no"
            if self.approval.granted is False
            else "unknown"
        )
        lines = [
            f"Intent: {self.intent}",
            f"Bundle: {self.bundle_id}",
            f"Classification: {self.classification}",
            f"Approval requested: {approvals}",
            f"Approval granted: {approval_granted}",
        ]
        if self.approval.actions:
            actions = ", ".join(f"{item.task_id}:{item.action_id}" for item in self.approval.actions)
            lines.append(f"Approval scope: {actions}")
        lines.append(f"Automatically handled: {', '.join(self.automatic_repairs) or 'none'}")
        lines.append(f"Authority used: {', '.join(self.authority_used) or 'none'}")
        if self.skipped:
            lines.append(f"Skipped: {', '.join(self.skipped)}")
        if self.blocked:
            lines.append(f"Blocked: {', '.join(self.blocked)}")
        task_lines = ", ".join(
            f"{task.task_id}={task.status}" + (f" ({task.reason})" if task.reason else "")
            for task in self.tasks
        )
        lines.append(f"Tasks: {task_lines or 'none'}")
        if self.stop_reason:
            lines.append(f"Stop reason: {self.stop_reason}")
        return "\n".join(lines)


@dataclass(frozen=True)
class IntentBundle:
    bundle_id: str
    intent: str
    tasks: Sequence[task_executor.Task]
    identity_digest: str = field(init=False)

    def __post_init__(self) -> None:
        digest = _bundle_digest(self.bundle_id, self.intent, self.tasks)
        object.__setattr__(self, "identity_digest", digest)

    def expand(self) -> tuple[BundledTask, ...]:
        return tuple(
            BundledTask(
                task=task,
                bundle_id=self.bundle_id,
                intent=self.intent,
                identity_digest=self.identity_digest,
            )
            for task in self.tasks
        )


def execute_intent_bundle(
    bundle: IntentBundle,
    *,
    authorizations: Mapping[str, AuthorizationRecord],
    admission_tokens: Mapping[str, task_executor.AdmissionToken],
    approval_requester: Callable[[ApprovalRequest], bool] | None = None,
) -> BundleExecutionReport:
    approval_actions, blocked, unknowns = _collect_prerequisite_state(bundle)
    approval_summary = ApprovalSummary(
        requested=bool(approval_actions),
        granted=None,
        prompt_count=0,
        actions=tuple(approval_actions),
    )
    skipped_tasks = tuple(task.task_id for task in bundle.tasks)
    if blocked:
        return _report_blocked(
            bundle,
            approval_summary,
            blocked,
            "Prerequisites blocked execution",
            skipped=skipped_tasks,
        )
    if unknowns:
        return _report_unknown(
            bundle,
            approval_summary,
            unknowns,
            skipped=skipped_tasks,
        )
    approval_grants: dict[str, bool] = {}
    if approval_actions:
        if approval_requester is None:
            return _report_refused(bundle, approval_summary, "Approval required but no requester provided")
        approval_summary = ApprovalSummary(
            requested=True,
            granted=None,
            prompt_count=1,
            actions=tuple(approval_actions),
        )
        approved = approval_requester(
            ApprovalRequest(
                bundle_id=bundle.bundle_id,
                intent=bundle.intent,
                identity_digest=bundle.identity_digest,
                actions=tuple(approval_actions),
            )
        )
        approval_summary = ApprovalSummary(
            requested=True,
            granted=approved,
            prompt_count=1,
            actions=tuple(approval_actions),
        )
        if not approved:
            return _report_refused(bundle, approval_summary, "Approval denied")
        approval_grants = {_approval_key(action): True for action in approval_actions}

    outcomes: list[TaskOutcome] = []
    automatic_repairs: list[str] = []
    authority_used: list[str] = []
    skipped: list[str] = []
    blocked_actions: list[str] = []
    for task in bundle.tasks:
        authorization = authorizations.get(task.task_id)
        admission_token = admission_tokens.get(task.task_id)
        if authorization is None or admission_token is None:
            skipped.append(task.task_id)
            outcomes.append(TaskOutcome(task_id=task.task_id, status="skipped", reason="missing authorization"))
            continue
        try:
            result = task_executor.execute_task(
                task,
                authorization=authorization,
                admission_token=admission_token,
                approval_grants=approval_grants,
            )
        except task_executor.TaskExhausted as exc:
            skipped.extend(_remaining_task_ids(bundle.tasks, task))
            return _report_exhausted(
                bundle,
                approval_summary,
                outcomes,
                automatic_repairs,
                authority_used,
                skipped,
                blocked_actions,
                exc.report.reason,
            )
        except task_executor.UnknownPrerequisiteError as exc:
            skipped.extend(_remaining_task_ids(bundle.tasks, task))
            return _report_unknown(
                bundle,
                approval_summary,
                blocked_actions + _assessment_labels(exc.assessments),
                outcomes=outcomes,
                automatic_repairs=automatic_repairs,
                authority_used=authority_used,
                skipped=skipped,
                stop_reason=str(exc),
            )
        except task_executor.EprApprovalRequired as exc:
            blocked_actions.extend(_approval_action_ids(exc.actions))
            skipped.extend(_remaining_task_ids(bundle.tasks, task))
            return _report_blocked(
                bundle,
                approval_summary,
                blocked_actions,
                "Approval required during execution",
                outcomes=outcomes,
                automatic_repairs=automatic_repairs,
                authority_used=authority_used,
                skipped=skipped,
            )
        except task_executor.TaskClosureError as exc:
            blocked_actions.extend(_assessment_labels(exc.assessments))
            skipped.extend(_remaining_task_ids(bundle.tasks, task))
            return _report_blocked(
                bundle,
                approval_summary,
                blocked_actions,
                str(exc),
                outcomes=outcomes,
                automatic_repairs=automatic_repairs,
                authority_used=authority_used,
                skipped=skipped,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            skipped.extend(_remaining_task_ids(bundle.tasks, task))
            return _report_failed(
                bundle,
                approval_summary,
                outcomes,
                automatic_repairs,
                authority_used,
                skipped,
                blocked_actions,
                str(exc) or exc.__class__.__name__,
            )
        outcomes.append(TaskOutcome(task_id=task.task_id, status=result.status))
        _record_epr_activity(result.epr_report, automatic_repairs, authority_used, approval_grants)
        if result.status != "completed":
            skipped.extend(_remaining_task_ids(bundle.tasks, task))
            return _report_failed(
                bundle,
                approval_summary,
                outcomes,
                automatic_repairs,
                authority_used,
                skipped,
                blocked_actions,
                "Task execution failed",
            )
    return BundleExecutionReport(
        classification="completed",
        intent=bundle.intent,
        bundle_id=bundle.bundle_id,
        identity_digest=bundle.identity_digest,
        approval=approval_summary,
        tasks=tuple(outcomes),
        automatic_repairs=tuple(sorted(set(automatic_repairs))),
        authority_used=tuple(sorted(set(authority_used))),
        skipped=tuple(skipped),
        blocked=tuple(blocked_actions),
        stop_reason=None,
    )


def _bundle_digest(bundle_id: str, intent: str, tasks: Sequence[task_executor.Task]) -> str:
    payload = {
        "bundle_id": bundle_id.strip(),
        "intent": intent.rstrip(),
        "tasks": [task_executor.canonicalise_task(task) for task in tasks],
    }
    serialised = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _collect_prerequisite_state(
    bundle: IntentBundle,
) -> tuple[list[ApprovalAction], list[str], list[str]]:
    approvals: list[ApprovalAction] = []
    blocked: list[str] = []
    unknowns: list[str] = []
    for task in bundle.tasks:
        for action, assessment in task_executor.assess_task_prerequisites(task):
            if assessment.status == "authority-required":
                approvals.append(_approval_action(task, action))
            elif assessment.status == "unknown":
                unknowns.append(f"{task.task_id}:{action.action_id}")
            elif assessment.status == "impossible":
                blocked.append(f"{task.task_id}:{action.action_id}")
    return approvals, blocked, unknowns


def _approval_action(task: task_executor.Task, action: task_executor.EprAction) -> ApprovalAction:
    return ApprovalAction(
        task_id=task.task_id,
        action_id=action.action_id,
        description=action.description or "EPR approval required",
        authority_impact=action.authority_impact,
        reversibility=action.reversibility,
        rollback_proof=action.rollback_proof,
    )


def _approval_key(action: ApprovalAction) -> str:
    return f"{action.task_id}:{action.action_id}"


def _report_refused(
    bundle: IntentBundle, approval_summary: ApprovalSummary, reason: str
) -> BundleExecutionReport:
    return BundleExecutionReport(
        classification="refused",
        intent=bundle.intent,
        bundle_id=bundle.bundle_id,
        identity_digest=bundle.identity_digest,
        approval=approval_summary,
        tasks=tuple(TaskOutcome(task_id=task.task_id, status="skipped", reason=reason) for task in bundle.tasks),
        automatic_repairs=(),
        authority_used=(),
        skipped=tuple(task.task_id for task in bundle.tasks),
        blocked=(),
        stop_reason=reason,
    )


def _report_blocked(
    bundle: IntentBundle,
    approval_summary: ApprovalSummary,
    blocked: Sequence[str],
    reason: str,
    *,
    outcomes: Sequence[TaskOutcome] = (),
    automatic_repairs: Sequence[str] = (),
    authority_used: Sequence[str] = (),
    skipped: Sequence[str] = (),
) -> BundleExecutionReport:
    return BundleExecutionReport(
        classification="blocked",
        intent=bundle.intent,
        bundle_id=bundle.bundle_id,
        identity_digest=bundle.identity_digest,
        approval=approval_summary,
        tasks=tuple(outcomes),
        automatic_repairs=tuple(automatic_repairs),
        authority_used=tuple(authority_used),
        skipped=tuple(skipped),
        blocked=tuple(blocked),
        stop_reason=reason,
    )


def _report_unknown(
    bundle: IntentBundle,
    approval_summary: ApprovalSummary,
    unknowns: Sequence[str],
    *,
    outcomes: Sequence[TaskOutcome] = (),
    automatic_repairs: Sequence[str] = (),
    authority_used: Sequence[str] = (),
    skipped: Sequence[str] = (),
    stop_reason: str | None = None,
) -> BundleExecutionReport:
    return BundleExecutionReport(
        classification="unknown_prerequisite",
        intent=bundle.intent,
        bundle_id=bundle.bundle_id,
        identity_digest=bundle.identity_digest,
        approval=approval_summary,
        tasks=tuple(outcomes),
        automatic_repairs=tuple(automatic_repairs),
        authority_used=tuple(authority_used),
        skipped=tuple(skipped),
        blocked=tuple(unknowns),
        stop_reason=stop_reason or "Unknown prerequisites blocked execution",
    )


def _report_exhausted(
    bundle: IntentBundle,
    approval_summary: ApprovalSummary,
    outcomes: Sequence[TaskOutcome],
    automatic_repairs: Sequence[str],
    authority_used: Sequence[str],
    skipped: Sequence[str],
    blocked: Sequence[str],
    reason: str,
) -> BundleExecutionReport:
    return BundleExecutionReport(
        classification="exhausted",
        intent=bundle.intent,
        bundle_id=bundle.bundle_id,
        identity_digest=bundle.identity_digest,
        approval=approval_summary,
        tasks=tuple(outcomes),
        automatic_repairs=tuple(automatic_repairs),
        authority_used=tuple(authority_used),
        skipped=tuple(skipped),
        blocked=tuple(blocked),
        stop_reason=reason,
    )


def _report_failed(
    bundle: IntentBundle,
    approval_summary: ApprovalSummary,
    outcomes: Sequence[TaskOutcome],
    automatic_repairs: Sequence[str],
    authority_used: Sequence[str],
    skipped: Sequence[str],
    blocked: Sequence[str],
    reason: str,
) -> BundleExecutionReport:
    return BundleExecutionReport(
        classification="failed",
        intent=bundle.intent,
        bundle_id=bundle.bundle_id,
        identity_digest=bundle.identity_digest,
        approval=approval_summary,
        tasks=tuple(outcomes),
        automatic_repairs=tuple(automatic_repairs),
        authority_used=tuple(authority_used),
        skipped=tuple(skipped),
        blocked=tuple(blocked),
        stop_reason=reason,
    )


def _record_epr_activity(
    report: task_executor.EprReport,
    automatic_repairs: list[str],
    authority_used: list[str],
    approval_grants: Mapping[str, bool],
) -> None:
    approved_keys = {key for key, approved in approval_grants.items() if approved}
    for action in report.actions:
        action_key = f"{action.action_id}"
        key_with_parent = None
        if approved_keys:
            key_with_parent = next((key for key in approved_keys if key.endswith(f":{action.action_id}")), None)
        if action.status == "completed":
            if key_with_parent or action_key in approved_keys:
                authority_used.append(action.action_id)
            else:
                automatic_repairs.append(action.action_id)


def _remaining_task_ids(tasks: Sequence[task_executor.Task], current: task_executor.Task) -> list[str]:
    seen = False
    remaining: list[str] = []
    for task in tasks:
        if task.task_id == current.task_id:
            seen = True
            continue
        if seen:
            remaining.append(task.task_id)
    return remaining


def _approval_action_ids(actions: Iterable[task_executor.EprAction]) -> list[str]:
    return [f"{action.parent_task_id}:{action.action_id}" for action in actions]


def _assessment_labels(assessments: Iterable[task_executor.PrerequisiteAssessment]) -> list[str]:
    return [assessment.action_id for assessment in assessments]
