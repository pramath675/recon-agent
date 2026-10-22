"""Pure verification logic. No I/O, no model calls: the status is computed ONLY from test results.

Passing tests are evidence of a fix, not proof of correctness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .runner import FAILED, NO_TESTS, PASSED, RunResult

VERIFIED = "VERIFIED"
UNVERIFIED = "UNVERIFIED"
COULD_NOT_REPRODUCE = "COULD NOT REPRODUCE"
ERROR = "ERROR"   # operational failure (config, API, budget, project); not a verification verdict


@dataclass
class Verdict:
    status: str
    reasons: List[str] = field(default_factory=list)
    checks: Dict[str, object] = field(default_factory=dict)


def check_baseline(runs: Sequence[RunResult]) -> Tuple[bool, List[str]]:
    """The bug counts as reproduced only if the repro test FAILED (a real assertion/exception
    failure, not a timeout or setup/collection error) on EVERY baseline run."""
    if not runs:
        return False, ["no baseline run of the reproduction test was recorded"]
    reasons = []
    for i, run in enumerate(runs, 1):
        if run.outcome == FAILED:
            continue
        if run.outcome == PASSED:
            reasons.append(f"reproduction test PASSED on the unmodified code (run {i}); the bug was not reproduced")
        else:
            reasons.append(f"baseline run {i} ended in {run.outcome} (not a clean test failure); "
                           "timeouts, collection errors and setup errors do not count as reproducing the bug")
    return (not reasons), reasons


def regressions(baseline: RunResult, after: RunResult) -> List[str]:
    """Tests that passed before the patch but do not pass after it."""
    return sorted(t for t, s in baseline.tests.items() if s == "passed" and after.tests.get(t) != "passed")


def evaluate(
    *,
    baseline_repro_runs: Sequence[RunResult],
    patch_error: Optional[str],
    tamper_problems: Sequence[str],
    post_repro_runs: Sequence[RunResult],
    baseline_existing: RunResult,
    post_existing: Optional[RunResult],
    require_existing_tests: bool = False,
) -> Verdict:
    checks: Dict[str, object] = {}
    ok, reasons = check_baseline(baseline_repro_runs)
    checks["baseline_failure_established"] = ok
    if not ok:
        return Verdict(COULD_NOT_REPRODUCE, reasons, checks)

    reasons = []
    checks["patch_valid"] = patch_error is None
    if patch_error:
        reasons.append(f"patch rejected: {patch_error}")
    checks["tests_untampered"] = not tamper_problems
    reasons.extend(tamper_problems)

    if patch_error:
        return Verdict(UNVERIFIED, reasons, checks)

    post_ok = bool(post_repro_runs) and all(r.outcome == PASSED for r in post_repro_runs)
    checks["repro_passes_after_patch"] = post_ok
    if not post_repro_runs:
        reasons.append("the reproduction test was not run after the patch")
    for i, run in enumerate(post_repro_runs, 1):
        if run.outcome != PASSED:
            reasons.append(f"reproduction test did not pass after the patch (run {i}: {run.outcome})")
    outcomes = {r.outcome for r in post_repro_runs}
    checks["repro_stable_across_reruns"] = len(outcomes) <= 1
    if len(outcomes) > 1:
        reasons.append("reproduction test results differed between reruns (possible flakiness)")

    existing_ok = False
    if post_existing is None:
        reasons.append("existing tests were not run after the patch")
    elif post_existing.outcome == PASSED:
        regs = regressions(baseline_existing, post_existing)   # catches deleted/skipped tests too
        checks["existing_regressions"] = regs
        if regs:
            reasons.append("existing tests regressed (missing or not passing): " + ", ".join(regs))
        else:
            existing_ok = True
    elif post_existing.outcome == NO_TESTS and baseline_existing.outcome == NO_TESTS:
        existing_ok = not require_existing_tests
        if require_existing_tests:
            reasons.append("project has no existing tests but they are required")
    elif post_existing.outcome == FAILED:
        regs = regressions(baseline_existing, post_existing)
        new_failures = sorted(set(post_existing.failed_ids) - set(baseline_existing.failed_ids))
        checks["existing_regressions"] = sorted(set(regs) | set(new_failures))
        if regs or new_failures:
            reasons.append("existing tests regressed: " + ", ".join(sorted(set(regs) | set(new_failures))))
        else:
            existing_ok = True    # only failures that already failed before the patch
            reasons.append("note: existing tests that already failed before the patch still fail")
    else:
        reasons.append(f"existing test suite ended in {post_existing.outcome} after the patch")
    checks["existing_tests_ok"] = existing_ok
    checks["existing_tests_present"] = bool(post_existing and post_existing.tests)

    hard_ok = checks["patch_valid"] and checks["tests_untampered"] and post_ok \
        and checks["repro_stable_across_reruns"] and existing_ok
    if hard_ok:
        return Verdict(VERIFIED, [r for r in reasons if r.startswith("note:")], checks)
    return Verdict(UNVERIFIED, [r for r in reasons if not r.startswith("note:")] or reasons, checks)
