"""Run pytest locally in a temporary copy and classify what actually happened.

The only command RECON ever executes is:  <this python> -m pytest <fixed flags> [targets]
LLM output can influence WHICH test file contents exist, never the command line.

Sandbox limits (honest list): the child runs with a scrubbed environment (no API keys),
a temp HOME, a wall-clock timeout, a process-group kill (POSIX) and CPU/file-size rlimits
(POSIX). It is NOT isolated from the network, the rest of the filesystem or your user account.
For untrusted repositories run RECON inside a container or VM.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

PASSED, FAILED, TIMEOUT, ERROR, NO_TESTS = "PASSED", "FAILED", "TIMEOUT", "ERROR", "NO_TESTS"
OUTPUT_TAIL_CHARS = 3000


@dataclass
class RunResult:
    label: str
    outcome: str
    exit_code: Optional[int]
    duration_s: float
    tests: Dict[str, str] = field(default_factory=dict)   # test id -> passed/failed/error/skipped
    output_tail: str = ""
    command: List[str] = field(default_factory=list)

    @property
    def failed_ids(self) -> List[str]:
        return sorted(k for k, v in self.tests.items() if v in ("failed", "error"))

    def to_dict(self, tail_chars: int = 1500) -> dict:
        counts: Dict[str, int] = {}
        for status in self.tests.values():
            counts[status] = counts.get(status, 0) + 1
        return {
            "label": self.label, "outcome": self.outcome, "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 3), "counts": counts,
            "failed_tests": self.failed_ids, "output_tail": self.output_tail[-tail_chars:],
            "command": self.command,
        }


def _clean_env(home: str) -> Dict[str, str]:
    keep = ["PATH", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "TZ"]
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update({
        "HOME": home, "USERPROFILE": home, "TMPDIR": home, "TEMP": home, "TMP": home,
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8",
    })
    return env


def _posix_limits(timeout: int):
    def apply() -> None:  # runs in the child between fork and exec
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (timeout + 5, timeout + 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
    return apply


def parse_junit(xml_path: Path) -> Dict[str, str]:
    tests: Dict[str, str] = {}
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError):
        return tests
    for case in root.iter("testcase"):
        tid = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("failure") is not None:
            tests[tid] = "failed"
        elif case.find("error") is not None:
            tests[tid] = "error"
        elif case.find("skipped") is not None:
            tests[tid] = "skipped"
        else:
            tests[tid] = "passed"
    return tests


def classify(exit_code: Optional[int], timed_out: bool, tests: Dict[str, str]) -> str:
    """Pure function: map pytest facts to one outcome. Distinguishes failure from timeout/setup error."""
    if timed_out:
        return TIMEOUT
    if exit_code == 0:
        return PASSED
    if exit_code == 1:
        return FAILED if any(v == "failed" for v in tests.values()) else ERROR
    if exit_code == 5:
        return NO_TESTS
    return ERROR   # 2 interrupted/collection error, 3 internal error, 4 usage error, signals, None


def run_pytest(
    root: Path,
    *,
    targets: Sequence[str] = (),
    ignore: Sequence[str] = (),
    timeout: int = 60,
    label: str = "pytest",
) -> RunResult:
    root = Path(root)
    scratch = Path(tempfile.mkdtemp(prefix="recon_run_"))
    xml_path, out_path = scratch / "junit.xml", scratch / "output.txt"
    cmd = [
        sys.executable, "-m", "pytest", "-q", "--no-header", "--color=no", "--tb=short",
        "-p", "no:cacheprovider", "-o", "junit_family=xunit2", f"--junitxml={xml_path}",
        *[f"--ignore={p}" for p in ignore], *targets,
    ]
    popen_kwargs = {}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
        popen_kwargs["preexec_fn"] = _posix_limits(timeout)
    else:
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    started, timed_out, exit_code = time.time(), False, None
    try:
        with open(out_path, "wb") as sink:
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(root), env=_clean_env(str(scratch)),
                    stdout=sink, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **popen_kwargs,
                )
            except OSError as exc:
                return RunResult(label, ERROR, None, 0.0, output_tail=f"could not start pytest: {exc}", command=cmd)
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == "posix":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
                proc.wait()
        tail = out_path.read_bytes()[-OUTPUT_TAIL_CHARS:].decode("utf-8", "replace")
        tests = parse_junit(xml_path)
        if timed_out:
            tail = f"[RECON] killed after {timeout}s timeout\n" + tail
        return RunResult(label, classify(exit_code, timed_out, tests), exit_code,
                         time.time() - started, tests, tail, cmd)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
