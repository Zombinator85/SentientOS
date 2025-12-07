from agents.forms import page_router


def test_next_page_walks_entire_flow():
    assert page_router.next_page("login") == "contact_info"
    assert page_router.next_page("contact_info") == "conditions"
    assert page_router.next_page("conditions") == "work_history"


def test_next_page_returns_none_at_terminal():
    assert page_router.next_page("work_history") is None
    assert page_router.next_page("unknown") is None


def test_page_index_is_deterministic():
    assert page_router.page_index("login") == 0
    assert page_router.page_index("work_history") == len(page_router.PAGE_FLOW) - 1
    assert page_router.page_index("missing") == -1
