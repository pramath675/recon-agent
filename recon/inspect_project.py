"""Pick the most relevant source files for the prompt without any model call or embeddings."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from .fs import ProjectError, iter_project_files
from .safety import GENERATED_DIR, is_protected_path

MAX_FILE_CHARS = 12000
_STOP = {
    "the", "and", "for", "with", "that", "this", "when", "from", "not", "but", "are", "was",
    "bug", "should", "does", "doesn", "returns", "return", "get", "gets", "have", "has",
    "expected", "actual", "instead", "wrong", "error", "issue", "report", "reported",
}


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower()) if t not in _STOP}


def build_context(root: Path, bug_report: str, max_chars: int) -> Tuple[str, List[str]]:
    """Return (prompt_text, included_relative_paths).

    Ranking is plain keyword overlap between the bug report and file path/content.
    Source files outrank test files; files that would not fit whole are skipped
    (partial files would break exact-match patching).
    """
    root = Path(root)
    keywords = _tokens(bug_report)
    all_rel: List[str] = []
    candidates = []
    for rel, full in iter_project_files(root, extra_ignore_dirs=[GENERATED_DIR]):
        all_rel.append(rel)
        if not rel.endswith(".py"):
            continue
        try:
            text = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if len(text) > MAX_FILE_CHARS or not text.strip():
            continue
        lowered = text.lower()
        score = sum(lowered.count(k) for k in keywords) + 5 * sum(1 for k in keywords if k in rel.lower())
        candidates.append((is_protected_path(rel), -score, len(text), rel, text))
    candidates.sort()  # source files first, then by descending score, then smaller first

    tree = "\n".join(all_rel[:150]) + ("\n... (truncated)" if len(all_rel) > 150 else "")
    parts, included, used = [], [], len(tree)
    for is_test, _neg, size, rel, text in candidates:
        block = f"=== FILE: {rel} ===\n{text}\n"
        if used + len(block) > max_chars:
            continue
        parts.append(block)
        included.append(rel)
        used += len(block)
    if not any(not is_protected_path(r) for r in included):
        raise ProjectError("no Python source file fit within the context budget; raise RECON_MAX_CONTEXT_CHARS")
    return f"PROJECT FILE TREE:\n{tree}\n\nSOURCE FILES:\n" + "\n".join(parts), included
