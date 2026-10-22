"""Orchestration: reproduce -> patch -> verify. Fixed pipeline, no loops beyond one repair per stage."""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import __version__
from .config import Config
from .fs import ProjectError, copy_project
from .inspect_project import build_context
from .llm import LLMClient, LLMError
from .patching import PatchError, apply_edits, make_diff, parse_patch
from .prompts import (PATCH_SYSTEM, REPRO_SYSTEM, describe_runs, patch_user_prompt, repro_user_prompt)
from .runner import FAILED, PASSED, RunResult, run_pytest
from .safety import GENERATED_DIR, GENERATED_TEST, diff_snapshots, scan_test_code, snapshot_protected
from .verify import COULD_NOT_REPRODUCE, ERROR, UNVERIFIED, VERIFIED, Verdict, check_baseline, evaluate

DISCLAIMER = ("Passing tests are evidence that the reported behaviour was fixed and that existing tests still pass. "
              "They are not a mathematical proof of correctness.")
LIMITATIONS = [
    "The generated reproduction test is itself LLM-written; a human should read it before trusting the verdict.",
    "A baseline failure for a reason unrelated to the reported bug would still count as 'reproduced'.",
    "Verification is only as strong as the existing test suite plus the one generated test.",
    "Tests run in a temp copy with a scrubbed environment and timeouts, but this is NOT a security sandbox "
    "(no network or filesystem isolation). Run RECON in a container/VM for untrusted code.",
    "Only Python projects whose tests run with 'python -m pytest' from the project root are supported.",
]


def _say_default(msg: str) -> None:
    print(msg, flush=True)


def run_recon(project_dir: Path, bug_report: str, cfg: Config, llm: LLMClient, out_dir: Path,
              say: Callable[[str], None] = _say_default) -> Dict[str, Any]:
    started = time.time()
    report: Dict[str, Any] = {
        "tool": "RECON", "version": __version__, "status": ERROR, "reasons": [],
        "disclaimer": DISCLAIMER, "project": str(project_dir), "model": llm.model_name,
        "bug_report": bug_report, "checks": {}, "baseline": {}, "patch": {"attempts": [], "changed_files": [], "diff": ""},
        "post_patch": {}, "generated_test": None, "limitations": LIMITATIONS,
    }
    work = Path(tempfile.mkdtemp(prefix="recon_"))
    try:
        _pipeline(Path(project_dir), bug_report, cfg, llm, work, report, say)
    except LLMError as exc:
        _finish(report, ERROR, [f"model stage failed: {exc}"])
    except (ProjectError, OSError) as exc:
        _finish(report, ERROR, [f"project/filesystem error: {exc}"])
    except Exception as exc:  # last-resort: always produce a report, never a traceback-only crash
        _finish(report, ERROR, [f"unexpected internal error: {type(exc).__name__}: {exc}"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
        report["api_usage"] = llm.usage.to_dict(llm.cfg.max_api_calls)
        report["duration_s"] = round(time.time() - started, 2)
        _write_artifacts(report, out_dir)
    return report


def _finish(report: Dict[str, Any], status: str, reasons: List[str], checks: Optional[dict] = None) -> None:
    report["status"] = status
    report["reasons"] = reasons
    if checks is not None:
        report["checks"] = checks


def _pipeline(src: Path, bug: str, cfg: Config, llm: LLMClient, work: Path,
              report: Dict[str, Any], say: Callable[[str], None]) -> None:
    if not src.is_dir():
        raise ProjectError(f"project directory not found: {src}")
    base = work / "base"
    stats = copy_project(src, base, skip_dirs=[GENERATED_DIR])
    report["project_copy"] = stats
    context, included = build_context(base, bug, cfg.max_context_chars)
    report["context_files"] = included
    say(f"[1/5] Copied project to a temp dir ({stats['files']} files). Sent {len(included)} file(s) as context: "
        + ", ".join(included))

    say("[2/5] Running the existing tests on the UNMODIFIED code...")
    existing_base = run_pytest(base, ignore=[GENERATED_DIR], timeout=cfg.test_timeout, label="baseline_existing")
    say(f"      existing tests: {existing_base.outcome} {_counts(existing_base)}")

    # ------------------------------------------------------------ stage 1: reproduction
    say("[3/5] Generating a reproduction test (model call 1)...")
    repro_code, base_runs, repro_notes = _reproduce(bug, context, cfg, llm, base, report, say)
    report["baseline"] = {"existing_tests": existing_base.to_dict(), "repro_runs": [r.to_dict() for r in base_runs],
                          "notes": repro_notes}
    ok, why = check_baseline(base_runs) if repro_code else (False, repro_notes or ["no valid reproduction test was produced"])
    if not ok:
        _finish(report, COULD_NOT_REPRODUCE, why + [n for n in repro_notes if n not in why],
                {"baseline_failure_established": False})
        say("      -> bug NOT reproduced; stopping before the patch stage (no patch call spent).")
        return
    report["generated_test"] = repro_code
    say(f"      bug reproduced: test FAILED on the original code in {len(base_runs)}/{len(base_runs)} runs.")

    # ------------------------------------------------------------ stage 2: patch + verify
    failure_tail = base_runs[0].output_tail[-1500:]
    verdict, last_changes, notes = None, {}, []
    prev_edits_text = feedback = None
    for attempt in (1, 2):
        stage = "patch" if attempt == 1 else "patch_repair"
        say(f"[4/5] Generating a patch (model call, attempt {attempt}/2)...")
        try:
            resp = llm.complete_json(stage, PATCH_SYSTEM,
                                     patch_user_prompt(bug, context, repro_code, failure_tail, prev_edits_text, feedback))
        except LLMError as exc:
            if attempt == 1:
                raise
            notes.append(f"repair attempt unavailable: {exc}")
            say(f"      repair attempt not possible: {exc}")
            break
        patched = work / f"patched{attempt}"
        shutil.copytree(base, patched)
        before = snapshot_protected(patched)
        patch_error, changes, post_runs, post_existing, tamper = None, {}, [], None, []
        try:
            changes = apply_edits(patched, parse_patch(resp))
        except PatchError as exc:
            patch_error = str(exc)
            say(f"      patch rejected: {patch_error}")
        if patch_error is None:
            say("[5/5] Verifying in the temp copy (repro test, reruns, existing tests)...")
            first = run_pytest(patched, targets=[GENERATED_TEST], timeout=cfg.test_timeout, label="post_repro_1")
            post_runs = [first]
            if first.outcome == PASSED:
                for i in range(2, cfg.repeats + 1):
                    post_runs.append(run_pytest(patched, targets=[GENERATED_TEST], timeout=cfg.test_timeout,
                                                label=f"post_repro_{i}"))
            post_existing = run_pytest(patched, ignore=[GENERATED_DIR], timeout=cfg.test_timeout, label="post_existing")
            tamper = diff_snapshots(before, snapshot_protected(patched))
        verdict = evaluate(baseline_repro_runs=base_runs, patch_error=patch_error, tamper_problems=tamper,
                           post_repro_runs=post_runs, baseline_existing=existing_base, post_existing=post_existing)
        last_changes = changes
        report["patch"]["attempts"].append({
            "attempt": attempt, "explanation": str(resp.get("explanation", ""))[:300],
            "patch_error": patch_error, "status": verdict.status, "reasons": verdict.reasons,
            "changed_files": sorted(changes), "diff": make_diff(changes) if changes else "",
            "post_repro_runs": [r.to_dict() for r in post_runs],
            "post_existing": post_existing.to_dict() if post_existing else None,
        })
        report["post_patch"] = report["patch"]["attempts"][-1]
        say(f"      attempt {attempt}: {verdict.status}" + (f" ({'; '.join(verdict.reasons)})" if verdict.reasons else ""))
        if verdict.status == VERIFIED:
            break
        prev_edits_text = json.dumps(resp.get("edits", resp), indent=1)[:3000]
        tails = post_runs[-1].output_tail[-800:] if post_runs else ""
        feedback = "; ".join(verdict.reasons) + (f"\nTest output:\n{tails}" if tails else "")

    assert verdict is not None
    report["patch"]["changed_files"] = sorted(last_changes)
    report["patch"]["diff"] = make_diff(last_changes) if last_changes else ""
    _finish(report, verdict.status, verdict.reasons + notes, verdict.checks)


def _reproduce(bug: str, context: str, cfg: Config, llm: LLMClient, base: Path, report: Dict[str, Any],
               say: Callable[[str], None]):
    """Up to two model calls (initial + one repair). Returns (code_or_None, last_runs, notes)."""
    notes: List[str] = []
    prev = feedback = None
    runs: List[RunResult] = []
    code: Optional[str] = None
    attempts = []
    for attempt in (1, 2):
        stage = "repro" if attempt == 1 else "repro_repair"
        if attempt == 2:
            say("      repro test was not accepted; using the single repair attempt (model call 2)...")
        try:
            resp = llm.complete_json(stage, REPRO_SYSTEM, repro_user_prompt(bug, context, prev, feedback))
        except LLMError as exc:
            if attempt == 1:
                raise
            notes.append(f"repair attempt unavailable: {exc}")
            break
        code = resp.get("test_code") if isinstance(resp.get("test_code"), str) else ""
        violations = scan_test_code(code)
        attempts.append({"attempt": attempt, "explanation": str(resp.get("explanation", ""))[:300],
                         "safety_violations": violations})
        report["repro_attempts"] = attempts
        if violations:
            notes.append(f"attempt {attempt}: generated test rejected by safety scan: " + "; ".join(violations))
            prev, feedback, runs = code, "Rejected by safety scan: " + "; ".join(violations), []
            continue
        target = base / GENERATED_TEST
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
        runs = [run_pytest(base, targets=[GENERATED_TEST], timeout=cfg.test_timeout, label="baseline_repro_1")]
        if runs[0].outcome == FAILED:
            for i in range(2, cfg.repeats + 1):
                runs.append(run_pytest(base, targets=[GENERATED_TEST], timeout=cfg.test_timeout,
                                       label=f"baseline_repro_{i}"))
        ok, _ = check_baseline(runs)
        if ok:
            return code, runs, notes
        prev, feedback = code, describe_runs(runs)
    return (code if runs else None), runs, notes


def _counts(run: RunResult) -> str:
    c: Dict[str, int] = {}
    for s in run.tests.values():
        c[s] = c.get(s, 0) + 1
    return "(" + ", ".join(f"{v} {k}" for k, v in sorted(c.items())) + ")" if c else ""


def _write_artifacts(report: Dict[str, Any], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recon_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report.get("generated_test"):
        (out_dir / "test_recon_repro.py").write_text(report["generated_test"], encoding="utf-8")
    diff = report.get("patch", {}).get("diff")
    if diff:
        (out_dir / "patch.diff").write_text(diff, encoding="utf-8")
