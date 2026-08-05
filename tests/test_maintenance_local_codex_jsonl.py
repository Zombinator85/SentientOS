import pytest
from sentientos.maintenance_local_codex_foreman import JsonlObservationParser
pytestmark=pytest.mark.no_legacy_skip
def test_jsonl_parser_captures_one_thread_and_completed_turn():
    p=JsonlObservationParser(); p.feed('{"type":"thread.started","thread_id":"t"}\n'); p.feed('{"type":"turn.completed","thread_id":"t"}\n'); s=p.summary(); assert s['thread_id']=='t' and s['completed_turn_count']==1
def test_jsonl_parser_rejects_malformed_or_conflicting_thread_stream():
    p=JsonlObservationParser(); p.feed('{"thread_id":"a"}\n');
    with pytest.raises(ValueError): p.feed('{"thread_id":"b"}\n')
    with pytest.raises(ValueError): JsonlObservationParser().feed('{bad')
def test_jsonl_parser_bounds_line_and_total_transcript_bytes():
    with pytest.raises(ValueError): JsonlObservationParser(max_line=2).feed('{}{}')
    p=JsonlObservationParser(max_total=3); p.feed('{}');
    with pytest.raises(ValueError): p.feed('{}')
def test_unknown_events_are_preserved_without_becoming_success():
    p=JsonlObservationParser(); p.feed('{"type":"new.event"}\n'); s=p.summary(); assert s['unknown_events'] and s['completed_turn_count']==0
