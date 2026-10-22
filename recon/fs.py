"""Filesystem helpers: safe project walking and copying.

Everything that reads or copies a user project goes through here so that
virtual environments, VCS data, caches, secrets, symlinks and very large
files are consistently excluded.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple


class ProjectError(Exception):
    """The project cannot be inspected or copied safely."""


IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    "node_modules", "build", "dist", ".idea", ".vscode", "site-packages",
    ".eggs", "htmlcov", "recon_output",
}
SECRET_NAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc",
    ".netrc", "credentials.json", "secrets.json", "service-account.json",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx")


def is_ignored_dir(name: str, extra: Iterable[str] = ()) -> bool:
    return name in IGNORE_DIRS or name in set(extra) or name.endswith(".egg-info")


def is_secret_name(name: str) -> bool:
    n = name.lower()
    return (
        n.startswith(".env")
        or n in SECRET_NAMES
        or n.endswith(SECRET_SUFFIXES)
        or "secret" in n
        or "credential" in n
    )


def iter_project_files(root: Path, extra_ignore_dirs: Iterable[str] = ()) -> Iterator[Tuple[str, Path]]:
    """Yield (posix_relative_path, absolute_path) for every safe, regular file."""
    root = Path(root)
    extra = tuple(extra_ignore_dirs)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            d for d in dirnames
            if not is_ignored_dir(d, extra) and not os.path.islink(os.path.join(dirpath, d))
        )
        for fname in sorted(filenames):
            full = Path(dirpath) / fname
            if full.is_symlink() or is_secret_name(fname) or not full.is_file():
                continue
            yield full.relative_to(root).as_posix(), full


def copy_project(
    src: Path,
    dst: Path,
    *,
    skip_dirs: Iterable[str] = (),
    max_file_bytes: int = 5_000_000,
    max_total_bytes: int = 100_000_000,
) -> Dict[str, object]:
    """Copy the safe subset of ``src`` into ``dst``. Never touches ``src``."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    total = files = 0
    skipped_large = []
    for rel, full in iter_project_files(src, skip_dirs):
        size = full.stat().st_size
        if size > max_file_bytes:
            skipped_large.append(rel)
            continue
        total += size
        if total > max_total_bytes:
            raise ProjectError(f"project is larger than {max_total_bytes // 1_000_000} MB; refusing to copy")
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full, target)
        files += 1
    if files == 0:
        raise ProjectError("no files found to copy (is the project path correct?)")
    return {"files": files, "bytes": total, "skipped_large_files": skipped_large}
