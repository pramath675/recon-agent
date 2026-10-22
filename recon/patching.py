"""Validate and apply LLM-proposed edits.

Edit format (chosen over unified diffs because LLMs often emit malformed hunks):
    {"edits": [{"path": "pkg/mod.py", "search": "<exact existing text>", "replace": "<new text>"}]}
Rules: existing .py source files only, search text must match exactly once,
tests/config/generated files are untouchable, result must still parse as Python.
"""
from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Tuple

from .fs import is_ignored_dir
from .safety import is_protected_path, scan_patch_text

MAX_EDITS = 5
MAX_PATCH_CHARS = 20000


class PatchError(Exception):
    """The proposed patch is malformed, unsafe or does not apply."""


@dataclass(frozen=True)
class Edit:
    path: str
    search: str
    replace: str


def parse_patch(obj: Any) -> List[Edit]:
    if not isinstance(obj, dict) or not isinstance(obj.get("edits"), list):
        raise PatchError("patch must be a JSON object with an 'edits' list")
    raw = obj["edits"]
    if not 1 <= len(raw) <= MAX_EDITS:
        raise PatchError(f"patch must contain 1 to {MAX_EDITS} edits, got {len(raw)}")
    edits, total = [], 0
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise PatchError(f"edit {i} is not an object")
        path, search, replace = item.get("path"), item.get("search"), item.get("replace")
        if not all(isinstance(x, str) for x in (path, search, replace)):
            raise PatchError(f"edit {i} needs string 'path', 'search' and 'replace'")
        if not search.strip():
            raise PatchError(f"edit {i} has an empty 'search' string")
        if search == replace:
            raise PatchError(f"edit {i} changes nothing")
        total += len(search) + len(replace)
        edits.append(Edit(path, search, replace))
    if total > MAX_PATCH_CHARS:
        raise PatchError(f"patch is larger than {MAX_PATCH_CHARS} characters")
    return edits


def resolve_safe(root: Path, rel: str) -> Tuple[str, Path]:
    """Return (normalised_relative_path, absolute_path) or raise PatchError."""
    if not rel or "\x00" in rel:
        raise PatchError("empty or invalid path")
    norm = rel.replace("\\", "/")
    pp = PurePosixPath(norm)
    if pp.is_absolute() or re.match(r"^[A-Za-z]:", norm):
        raise PatchError(f"absolute paths are not allowed: {rel}")
    if ".." in pp.parts:
        raise PatchError(f"path traversal is not allowed: {rel}")
    if pp.suffix != ".py":
        raise PatchError(f"only .py files may be patched: {rel}")
    if is_protected_path(norm):
        raise PatchError(f"tests, test config and generated files may not be modified: {rel}")
    if any(is_ignored_dir(part) for part in pp.parts[:-1]):
        raise PatchError(f"path is inside an ignored directory: {rel}")
    root = Path(root)
    candidate = root / pp
    if candidate.is_symlink():
        raise PatchError(f"symlinks are not allowed: {rel}")
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (ValueError, OSError):
        raise PatchError(f"path escapes the project: {rel}")
    if not resolved.is_file():
        raise PatchError(f"file does not exist (creating new files is not supported): {rel}")
    return pp.as_posix(), resolved


def apply_edits(root: Path, edits: List[Edit]) -> Dict[str, Tuple[str, str]]:
    """Apply edits under ``root`` (a TEMPORARY copy). Returns {path: (old_text, new_text)}.

    Everything is validated in memory first; files are written only if all edits succeed.
    """
    originals: Dict[str, Tuple[str, bool, Path]] = {}
    current: Dict[str, str] = {}
    for e in edits:
        key, target = resolve_safe(root, e.path)
        if key not in current:
            try:
                text = target.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                raise PatchError(f"file is not valid UTF-8: {key}")
            crlf = "\r\n" in text
            norm = text.replace("\r\n", "\n")
            originals[key] = (norm, crlf, target)
            current[key] = norm
        search, replace = e.search.replace("\r\n", "\n"), e.replace.replace("\r\n", "\n")
        n = current[key].count(search)
        if n == 0:
            raise PatchError(f"search text not found in {key} (must match existing text exactly)")
        if n > 1:
            raise PatchError(f"search text appears {n} times in {key}; it must be unique")
        bad = scan_patch_text(replace)
        if bad:
            raise PatchError("; ".join(bad))
        current[key] = current[key].replace(search, replace, 1)
    for key, new_text in current.items():
        try:
            ast.parse(new_text)
        except SyntaxError as exc:
            raise PatchError(f"patched {key} is not valid Python: {exc.msg} (line {exc.lineno})")
    changes: Dict[str, Tuple[str, str]] = {}
    for key, new_text in current.items():
        old_text, crlf, target = originals[key]
        if new_text == old_text:
            continue
        target.write_bytes((new_text.replace("\n", "\r\n") if crlf else new_text).encode("utf-8"))
        changes[key] = (old_text, new_text)
    if not changes:
        raise PatchError("patch produced no change")
    return changes


def make_diff(changes: Dict[str, Tuple[str, str]]) -> str:
    chunks = []
    for key in sorted(changes):
        old, new = changes[key]
        chunks.extend(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{key}", tofile=f"b/{key}",
        ))
    return "".join(chunks)
