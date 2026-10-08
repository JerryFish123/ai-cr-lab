"""URL gate for dashboard mock mode (no Streamlit dependency)."""
from __future__ import annotations

from typing import Mapping


def is_mock_query_unlocked(query_params: Mapping[str, str] | None) -> bool:
    """True when URL carries ?query=1 (demo/mock feature unlocked)."""
    if not query_params:
        return False
    raw = query_params.get("query")
    if raw is None:
        return False
    return str(raw).strip() == "1"
