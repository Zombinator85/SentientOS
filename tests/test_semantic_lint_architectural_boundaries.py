from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1]; pytestmark=pytest.mark.no_legacy_skip
def test_semantic_lint_does_not_ban_established_technical_vocabulary():
 source=(ROOT/'scripts/semantic_lint.sh').read_text()
 assert all(x not in source for x in ('relationship([^a-zA-Z]','connection([^a-zA-Z]','reward([^a-zA-Z]','reinforce([^a-zA-Z]','heartbeat([^a-zA-Z]','trust([^a-zA-Z]'))
 assert 'unsupported present-tense phenomenal claim' in source
def test_semantic_rules_prefer_contextual_review_to_token_bans():
 rules=(ROOT/'SEMANTIC_REGRESSION_RULES.md').read_text()
 assert 'not by banning ordinary engineering words' in rules
 assert 'agency, autonomy' in rules
 assert 'Do not grow the linter into a brittle censorship regex' in rules
