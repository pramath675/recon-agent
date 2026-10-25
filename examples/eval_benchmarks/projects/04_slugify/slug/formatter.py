"""URL slug formatting utilities."""
from __future__ import annotations
import re


def slugify(text: str, max_len: int = 50) -> str:
    """Convert arbitrary text into a clean URL-friendly slug.

    Replaces non-alphanumeric characters with hyphens, collapses multiple hyphens,
    lowercases text, and truncates to max_len.
    """
    if not text or not text.strip():
        return ""
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    if max_len and len(clean) > max_len:
        clean = clean[:max_len]
        # BUG: Truncating may slice directly at a hyphen, leaving a trailing separator
        # (e.g. 'quick-brown-fox' with max_len=12 truncates to 'quick-brown-').
        # It should strip trailing hyphens after truncating.
    return clean
