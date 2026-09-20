# Semantic Regression Rules

Semantic accuracy is determined primarily by review—not by banning ordinary engineering words. `scripts/semantic_lint.sh` checks only a small set of high-confidence, unsupported present-tense phenomenal assertions.

The linter permits accurate uses of agency, autonomy, goals, plans, heartbeat/liveness, connections, relationships, trustworthiness, rewards, reinforcement learning, reflection, self-models, affect, and embodiment. Whether those claims are correct is contextual and cannot be decided by a token scan.

An added line fails when it directly claims that SentientOS or its current system/model is sentient, phenomenally conscious, feels emotion or pain, suffers, experiences pleasure, or is alive. Explicit negation and research framing are allowed. Reviewers must still reject indirect unsupported claims. Do not grow the linter into a brittle censorship regex.
