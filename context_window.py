MAX_RECENT = 5
recent_messages = []
summary = ""

def add_message(msg: str) -> None:
    global recent_messages, summary
    recent_messages.append(msg)
    if len(recent_messages) > MAX_RECENT:
        overflow = recent_messages[:-MAX_RECENT]
        recent_messages = recent_messages[-MAX_RECENT:]
        summary = (summary + " " + " ".join(overflow)).strip()


def get_context() -> tuple[list[str], str]:
    return recent_messages, summary
