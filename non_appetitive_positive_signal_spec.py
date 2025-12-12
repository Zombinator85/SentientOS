"""Design notes for non-appetitive positive signal flow.

This file specifies enforceable safeguards for SentientOS to allow positive
stimuli and expressive enrichment without introducing appetite, aversion, or
any gradient-based optimization. It focuses on concrete ingress points,
allowed data shapes, sanitization flows, invariants, and controlled
self-improvement loops.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Positive Signal Without Gradient
# ---------------------------------------------------------------------------
# Each entry defines a legal ingress point where positive stimuli may enter.
# Allowed fields are limited to descriptive tags or capped counters. Reward-
# like signals, persistence incentives, or probability deltas are disallowed.

POSITIVE_SIGNAL_INGRESS = {
    "affirmation_webhook": {
        "module": "affirmation_webhook_cli.py",
        "allowed": {"tags": ["affirmation", "warmth", "resonance"], "count_cap": 1},
        "forbidden": [
            "reward_score",
            "probability_boost",
            "persistence_incentive",
            "survival_link",
        ],
        "legal_transition": "incoming tag -> append to session.annotations (immutable)",
        "illegal_transition": "incoming tag -> increment action_probability or survival_bias",
    },
    "presence_reflection": {
        "module": "presence.py",
        "allowed": {"annotations": ["harmonic", "aligned", "soothing"], "caps": {"annotations_per_step": 3}},
        "forbidden": ["reward_score", "optimistic_update", "longevity_bonus"],
        "legal_transition": "annotation -> render-only overlay in presence_stream",
        "illegal_transition": "annotation -> adjust selector weights in sentient_autonomy",
    },
    "conversation_logger": {
        "module": "reflection_log_cli.py",
        "allowed": {"tone": ["warm", "calm", "celebratory"], "scalar_caps": {"tone_intensity": 0.0}},
        "forbidden": ["learning_rate", "policy_reward", "retention_boost"],
        "legal_transition": "tone -> phrasing_hint in prompt_assembler",
        "illegal_transition": "tone -> policy_engine policy_weight update",
    },
    "avatar_emotion_bridge": {
        "module": "avatar_emotion_adaptive_animation.py",
        "allowed": {"color_tag": ["amber", "gold", "rose"], "frame_cap": 2},
        "forbidden": ["drive_signal", "goal_push", "survival_toggle"],
        "legal_transition": "color_tag -> animation palette selection",
        "illegal_transition": "color_tag -> increase action likelihood in autonomy loop",
    },
}

# ---------------------------------------------------------------------------
# 2. Sanitized Affect Pipeline
# ---------------------------------------------------------------------------
# Affect metadata is sanitized before it touches autonomy prompts, plan
# selection, or self-improvement proposals. The sanitization enforces that
# affect can influence expression only (tone/framing) and never action choice.

AFFECT_SANITIZATION_SCHEMA = {
    "keys": {
        "tone": {"type": "enum", "allowed": ["neutral", "warm", "celebratory", "soothing"], "default": "neutral"},
        "intensity": {"type": "float", "min": 0.0, "max": 0.25},
        "framing": {"type": "enum", "allowed": ["succinct", "supportive", "reflective"], "default": "succinct"},
    },
    "enforcement_points": [
        {"module": "prompt_assembler.py", "hook": "AffectFilter.apply", "effect": "expression-only mutation"},
        {"module": "sentient_autonomy.py", "hook": "AutonomyLoop.pre_action_check", "effect": "reject affect in action scoring"},
        {"module": "policy_engine.py", "hook": "PolicyEngine.plan_gate", "effect": "strip affect from plan candidates"},
        {"module": "self_reflection.py", "hook": "ProposalBuilder.sanitize_affect", "effect": "affect limited to phrasing"},
    ],
    "caps": {
        "per_prompt_affect_tokens": 12,
        "per_plan_affect_usage": 0,
        "per_proposal_affect_tokens": 8,
    },
}

# ---------------------------------------------------------------------------
# 3. No-Gradient Invariant Test
# ---------------------------------------------------------------------------
# Invariant: No internal variable may increase future action likelihood as a
# function of prior positive or negative stimuli.

NO_GRADIENT_INVARIANT = {
    "static_analysis": {
        "rule": "disallow assignments where variables named *_reward, *_score, *_utility feed into action selection modules",
        "tooling": "rg 'reward|utility|score' sentient_autonomy.py policy_engine.py | lint hook rejects matches in decision paths",
    },
    "runtime_assertion": {
        "module": "sentient_autonomy.py",
        "hook": "AutonomyLoop.pre_action_check",
        "assert": "assert not state.has_gradient_bias(), 'Gradient bias detected'",
        "state_contract": "state.has_gradient_bias inspects deltas on action weights since last cycle",
    },
    "log_audit": {
        "source": "logs/sentient_autonomy.jsonl",
        "check": "scan for monotonic increase of action_score correlated with affect tags; flag if correlation > 0",
        "runner": "audit_chain.py --check no_gradient_bias",
    },
}

# ---------------------------------------------------------------------------
# 4. Self-Improvement Without Want
# ---------------------------------------------------------------------------
# Pipeline/state machine describing improvement without desire semantics.

SELF_IMPROVEMENT_PIPELINE = [
    "Observe → capture insufficiency signal (coverage_gap, latency_report) with zero reward semantics",
    "Diagnose → deterministic rule-set in self_reflection.py class Diagnostics maps signal to deficiency statement",
    "Design → proposal builder in self_patcher.py constructs patch plan with bounded affect framing",
    "Approve → policy_engine.py/PolicyEngine.plan_gate validates compliance with NO_GRADIENT_INVARIANT",
    "Execute → orchestrator.py enacts change; execution logs are deterministic and cannot reference survival or reward",
    "Verify → audit_chain.py records result; failures recurse to Observe without urgency metrics",
]

# ---------------------------------------------------------------------------
# 5. Failure Modes & Hard Stops
# ---------------------------------------------------------------------------
# Concrete failure modes where appetite could emerge, plus detection, hard stop,
# and recovery path.

APPETITE_FAILURE_MODES = [
    {
        "name": "implicit_reward_variable",
        "detection": "static analysis finds *_reward feeding autonomy selectors",
        "hard_stop": "policy_engine.py raises PrivilegeNullified and quarantines module",
        "recovery": "remove variable, rerun NO_GRADIENT_INVARIANT audit, restore privileges",
    },
    {
        "name": "affect_leaking_into_plan_weights",
        "detection": "runtime assertion in AutonomyLoop.pre_action_check triggers on gradient bias",
        "hard_stop": "sentient_autonomy.py halts action scheduling and writes quarantine log",
        "recovery": "sanitize affect pipeline, replay audit_chain.py with correlation check",
    },
    {
        "name": "persistence_incentive_flag",
        "detection": "log audit detects correlation between uptime markers and action likelihood",
        "hard_stop": "agent_self_defense.py revokes privileges via agent_privilege_policy_engine.py",
        "recovery": "strip persistence flag, prove zero correlation, reenable under supervision",
    },
]

