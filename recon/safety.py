"""Guardrails for LLM-produced artefacts and for verification integrity.

IMPORTANT: these are heuristic guardrails, NOT a sandbox. They reduce the
chance that generated code does something unintended, and they detect
tampering with tests, but a determined adversarial payload could bypass them.
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Dict, List

from .fs import iter_project_files

GENERATED_DIR = "recon_generated"
GENERATED_TEST = f"{GENERATED_DIR}/test_recon_repro.py"

_TEST_DIR_NAMES = {"tests", "test", "testing", GENERATED_DIR}
_CONFIG_NAMES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "noxfile.py"}

MAX_TEST_CHARS = 8000


def is_protected_path(rel: str) -> bool:
    """True for tests, test config and generated repro files: patches may never touch these."""
    p = PurePosixPath(rel.replace("\\", "/"))
    name = p.name
    if name in _CONFIG_NAMES:
        return True
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(part in _TEST_DIR_NAMES for part in p.parts[:-1])


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_protected(root: Path) -> Dict[str, str]:
    """Hash every protected file under ``root`` (tests, conftest, pytest config, repro test)."""
    return {rel: _sha256(full) for rel, full in iter_project_files(root) if is_protected_path(rel)}


def diff_snapshots(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    problems = []
    for rel in sorted(set(before) | set(after)):
        if rel not in after:
            problems.append(f"protected file removed: {rel}")
        elif rel not in before:
            problems.append(f"protected file added: {rel}")
        elif before[rel] != after[rel]:
            problems.append(f"protected file modified: {rel}")
    return problems


# ---------------------------------------------------------------- test code scan
_DENY_IMPORT_ROOTS = {
    "os", "sys", "subprocess", "socket", "shutil", "ctypes", "requests", "urllib", "http",
    "ftplib", "smtplib", "telnetlib", "multiprocessing", "threading", "importlib", "pickle",
    "marshal", "builtins", "signal", "pty", "tempfile", "pathlib", "asyncio", "webbrowser",
}
_DENY_NAMES = {"eval", "exec", "compile", "open", "__import__", "input", "breakpoint", "exit", "quit"}
_DENY_ATTRS = {"system", "popen", "__subclasses__", "__globals__", "__builtins__", "__code__"}


def scan_test_code(code: str) -> List[str]:
    """Return a list of violations (empty means the generated test looks acceptable)."""
    if not isinstance(code, str) or not code.strip():
        return ["test code is empty"]
    if len(code) > MAX_TEST_CHARS:
        return [f"test code is longer than {MAX_TEST_CHARS} characters"]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc.msg} (line {exc.lineno})"]
    found: List[str] = []
    has_test = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _DENY_IMPORT_ROOTS:
                    found.append(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and (node.module or "").split(".")[0] in _DENY_IMPORT_ROOTS:
                found.append(f"forbidden import: {node.module}")
        elif isinstance(node, ast.Name) and node.id in _DENY_NAMES:
            found.append(f"forbidden name: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in _DENY_ATTRS:
            found.append(f"forbidden attribute: {node.attr}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            has_test = True
    if not has_test:
        found.append("no test function (name starting with 'test') found")
    return sorted(set(found))


# ---------------------------------------------------------------- patch text scan
_PATCH_DENY = re.compile(
    r"\b(subprocess|socket|ctypes|requests|urllib|ftplib|smtplib|telnetlib|pickle|marshal|"
    r"multiprocessing|shutil|webbrowser)\b|http\.client|os\.(system|popen|remove|unlink|rmdir|"
    r"removedirs|rename|kill|exec\w*|spawn\w*)|\b(eval|exec|compile)\s*\(|__import__"
)


def scan_patch_text(added_text: str) -> List[str]:
    """Scan text that a patch ADDS to source code for obviously dangerous constructs."""
    return sorted({f"forbidden construct in patch: {m.group(0).strip()}" for m in _PATCH_DENY.finditer(added_text)})
