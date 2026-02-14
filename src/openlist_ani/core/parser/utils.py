"""Utility functions for parser tools."""

import re
from typing import Optional


def parse_json_from_markdown(text: str) -> Optional[str]:
    """Extract JSON string from markdown code block or plain text.

    Args:
        text: Text containing JSON, possibly in markdown code blocks

    Returns:
        Extracted JSON string or None if not found
    """
    # Try to find JSON in markdown code block
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try to find JSON by curly braces
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return text[start:end]
    except ValueError:
        return None
