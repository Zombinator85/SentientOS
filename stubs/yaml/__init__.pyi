from typing import Any, IO

def safe_load(stream: str | bytes | IO[str] | IO[bytes]) -> Any: ...

def safe_dump(
    data: Any,
    stream: IO[str] | None = ...,
    *,
    sort_keys: bool = ...,
) -> str | None: ...
