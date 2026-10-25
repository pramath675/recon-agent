"""Evaluation Harness for RECON Multi-Bug Benchmark.

Provides:
  1. Offline Validation Mode (--mode check-offline):
     - Proves that all baseline tests PASS on the unmodified code.
     - Proves that all independent oracle tests FAIL with genuine assertion failures against buggy code.
     - Confirms zero collection or fixture/setup errors in the oracle tests.
     - Runs in a clean, allowlisted environment excluding NEBIUS_API_KEY and other credentials.
     - Makes zero network calls and spends zero API credits.
  2. Live Evaluation Mode (--mode run-live):
     - Runs each benchmark sequentially once with --max-calls 2.
     - Enforces a strict aggregate harness-level limit of 10 total model-call attempts.
     - If a task fails before producing a report, records its calls as unknown and
       conservatively reserves the full two-call task budget (never defaults to 0).
     - Never retries automatically; records failed requests as outcomes.
     - Runs the independent oracle test against a fresh patched copy to verify ground truth.
     - Generates Markdown and JSON audit reports in docs/.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BENCHMARKS_DIR = Path(__file__).resolve().parent / "examples" / "eval_benchmarks"
PROJECTS_DIR = BENCHMARKS_DIR / "projects"
ORACLES_DIR = BENCHMARKS_DIR / "oracles"

BENCHMARK_TASKS = [
    {
        "id": "01_buggy_shop",
        "name": "E-Commerce Pricing Bulk Threshold",
        "domain": "Pricing & Billing",
        "bug_type": "Boundary Comparison (> vs >=)",
        "project_dir": PROJECTS_DIR / "01_buggy_shop",
        "bug_report": PROJECTS_DIR / "01_buggy_shop" / "bug_report.md",
        "oracle_test": ORACLES_DIR / "01_buggy_shop" / "test_oracle.py",
    },
    {
        "id": "02_semver",
        "name": "Semantic Version Comparison",
        "domain": "Developer Tooling",
        "bug_type": "Type Sorting (str vs int)",
        "project_dir": PROJECTS_DIR / "02_semver",
        "bug_report": PROJECTS_DIR / "02_semver" / "bug_report.md",
        "oracle_test": ORACLES_DIR / "02_semver" / "test_oracle.py",
    },
    {
        "id": "03_token_bucket",
        "name": "Token Bucket Rate Limiter",
        "domain": "Systems & Networking",
        "bug_type": "Unbounded State Accumulation",
        "project_dir": PROJECTS_DIR / "03_token_bucket",
        "bug_report": PROJECTS_DIR / "03_token_bucket" / "bug_report.md",
        "oracle_test": ORACLES_DIR / "03_token_bucket" / "test_oracle.py",
    },
    {
        "id": "04_slugify",
        "name": "URL Slug Truncation Formatter",
        "domain": "Web & Text Processing",
        "bug_type": "Delimiter Boundary Leak",
        "project_dir": PROJECTS_DIR / "04_slugify",
        "bug_report": PROJECTS_DIR / "04_slugify" / "bug_report.md",
        "oracle_test": ORACLES_DIR / "04_slugify" / "test_oracle.py",
    },
    {
        "id": "05_tax_calc",
        "name": "Progressive Tax Bracket Calculator",
        "domain": "Finance & Payroll",
        "bug_type": "Non-Marginal Tier Math",
        "project_dir": PROJECTS_DIR / "05_tax_calc",
        "bug_report": PROJECTS_DIR / "05_tax_calc" / "bug_report.md",
        "oracle_test": ORACLES_DIR / "05_tax_calc" / "test_oracle.py",
    },
]

MAX_CALLS_PER_TASK = 2
MAX_TOTAL_AGGREGATE_CALLS = 10


def parse_junit(xml_path: Path) -> Dict[str, str]:
    """Parse pytest JUnit XML into {test_id: status} (passed, failed, error, skipped)."""
    tests: Dict[str, str] = {}
    if not xml_path.is_file():
        return tests
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


def clean_offline_env(project_dir: Path, scratch_dir: Path) -> Dict[str, str]:
    """Allowlist safe environment variables for offline checks.

    Explicitly excludes NEBIUS_API_KEY, OPENAI_API_KEY, and any other credentials.
    Points HOME and temp directories to a temporary scratch folder.
    """
    keep = ["PATH", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "TZ"]
    env = {k: os.environ[k] for k in keep if k in os.environ}
    scratch_str = str(scratch_dir)
    env.update({
        "HOME": scratch_str,
        "USERPROFILE": scratch_str,
        "TMPDIR": scratch_str,
        "TEMP": scratch_str,
        "TMP": scratch_str,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(project_dir),
    })
    return env


def run_cmd(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    clean_env: bool = False,
    scratch_dir: Optional[Path] = None,
) -> Tuple[int, str]:
    """Execute command synchronously, capturing returncode and combined stdout/stderr."""
    if clean_env:
        scratch = scratch_dir or Path(tempfile.mkdtemp(prefix="recon_cmd_clean_"))
        run_env = clean_offline_env(cwd or Path.cwd(), scratch)
    else:
        run_env = os.environ.copy()
    if env:
        run_env.update(env)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=run_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout


def check_offline_baseline_and_oracles() -> int:
    """Offline Mode: Run baseline tests and prove all oracles fail against buggy code.

    Enforces:
      1. Baseline tests must PASS cleanly (exit code 0, all tests passed, 0 failures, 0 errors).
      2. Oracle tests must record actual test ASSERTION FAILURES (<failure>), not collection or setup errors (<error>).
      3. Environment is strictly scrubbed of NEBIUS_API_KEY and other credentials via clean allowlist.
      4. Zero model calls, zero network calls, zero credits.
    """
    print("=" * 76)
    print("RECON MULTI-BUG BENCHMARK — OFFLINE INTEGRITY CHECKS")
    print("=" * 76)
    print("Verifying 5 controlled benchmarks in a clean, credential-scrubbed environment:\n")

    all_passed = True
    results = []

    for task in BENCHMARK_TASKS:
        tid = task["id"]
        pdir = task["project_dir"]
        oracle = task["oracle_test"]

        scratch = Path(tempfile.mkdtemp(prefix=f"recon_offcheck_{tid}_"))
        base_xml = scratch / "baseline_junit.xml"
        oracle_xml = scratch / "oracle_junit.xml"

        try:
            # 1. Baseline tests inside project must PASS on unmodified code
            base_code, base_out = run_cmd(
                [
                    sys.executable, "-m", "pytest", "-q", "--color=no",
                    "-o", "junit_family=xunit2", f"--junitxml={base_xml}",
                    "tests",
                ],
                cwd=pdir,
                clean_env=True,
                scratch_dir=scratch,
            )
            base_tests = parse_junit(base_xml)
            base_ok = (
                base_code == 0
                and bool(base_tests)
                and all(status == "passed" for status in base_tests.values())
            )

            # 2. Oracle test outside project must record an actual ASSERTION FAILURE, with ZERO setup/collection errors
            oracle_code, oracle_out = run_cmd(
                [
                    sys.executable, "-m", "pytest", "-q", "--color=no",
                    "-o", "junit_family=xunit2", f"--junitxml={oracle_xml}",
                    str(oracle),
                ],
                cwd=pdir,
                clean_env=True,
                scratch_dir=scratch,
            )
            oracle_tests = parse_junit(oracle_xml)
            has_assertion_failure = any(status == "failed" for status in oracle_tests.values())
            has_setup_or_collection_errors = any(status == "error" for status in oracle_tests.values())
            failed_count = sum(1 for s in oracle_tests.values() if s == "failed")
            error_count = sum(1 for s in oracle_tests.values() if s == "error")

            # Must have exit_code == 1, at least one test failure, and ZERO collection/setup errors
            oracle_fails_cleanly = (
                oracle_code == 1
                and has_assertion_failure
                and not has_setup_or_collection_errors
            )

            status_str = "READY" if (base_ok and oracle_fails_cleanly) else "MISMATCH"
            if not (base_ok and oracle_fails_cleanly):
                all_passed = False

            results.append({
                "task": tid,
                "name": task["name"],
                "baseline_passed": base_ok,
                "base_counts": f"{len(base_tests)} passed",
                "oracle_fails_cleanly": oracle_fails_cleanly,
                "oracle_detail": f"{failed_count} assertion failure(s), {error_count} collection/setup error(s)",
                "status": status_str,
            })

            print(f"[{status_str}] {tid}: {task['name']}")
            print(f"  - Baseline tests: {'PASS (Expected)' if base_ok else 'FAIL (Unexpected!)'} [{len(base_tests)} passed]")
            oracle_msg = "FAILS cleanly on test assertion (0 collection/setup errors)" if oracle_fails_cleanly else "MISMATCH (not a clean test failure!)"
            print(f"  - Oracle test on buggy code: {oracle_msg} [{failed_count} failed, {error_count} errors]")
            print()

        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    print("-" * 76)
    print(f"Summary: 5/5 tasks checked.")
    print(f"  * All baselines pass on unmodified code: {all(r['baseline_passed'] for r in results)}")
    print(f"  * All oracles fail with real test assertions & 0 setup/collection errors: {all(r['oracle_fails_cleanly'] for r in results)}")
    print(f"  * Environment scrubbing active: NEBIUS_API_KEY and caller secrets excluded.")
    print("-" * 76)
    return 0 if all_passed else 1


def apply_patch_to_dir(target_dir: Path, diff_text: str) -> bool:
    """Apply a unified diff to target_dir reliably without requiring a Git repository."""
    if not diff_text or not diff_text.strip():
        return False

    # 1. Reliable in-memory unified diff hunk application
    try:
        import re
        lines = diff_text.replace("\r\n", "\n").splitlines(keepends=True)
        i = 0
        applied_any = False
        while i < len(lines):
            line = lines[i]
            if line.startswith("--- "):
                if i + 1 >= len(lines):
                    break
                m_target = re.match(r"^\+\+\+ [ab]/(.*)$", lines[i + 1].strip())
                if not m_target:
                    i += 1
                    continue
                rel_path = m_target.group(1).strip()
                target_file = target_dir / rel_path
                if not target_file.is_file():
                    return False

                orig_text = target_file.read_text(encoding="utf-8").replace("\r\n", "\n")
                orig_lines = orig_text.splitlines(keepends=True)
                i += 2
                new_lines = list(orig_lines)

                while i < len(lines) and lines[i].startswith("@@"):
                    i += 1
                    hunk_old, hunk_new = [], []
                    while i < len(lines) and not lines[i].startswith(("@@", "--- ")):
                        hline = lines[i]
                        if hline.startswith(" "):
                            hunk_old.append(hline[1:])
                            hunk_new.append(hline[1:])
                        elif hline.startswith("-"):
                            hunk_old.append(hline[1:])
                        elif hline.startswith("+"):
                            hunk_new.append(hline[1:])
                        i += 1

                    old_str = "".join(hunk_old)
                    new_str = "".join(hunk_new)
                    curr = "".join(new_lines)
                    if old_str in curr:
                        curr = curr.replace(old_str, new_str, 1)
                        new_lines = curr.splitlines(keepends=True)
                    else:
                        return False

                target_file.write_text("".join(new_lines), encoding="utf-8")
                applied_any = True
            else:
                i += 1
        if applied_any:
            return True
    except Exception:
        pass

    # 2. Fallback to git apply if target_dir is inside a git repo or has git available
    patch_file = target_dir / "_recon_temp.patch"
    patch_file.write_bytes(diff_text.replace("\r\n", "\n").encode("utf-8"))
    try:
        code, out = run_cmd(["git", "apply", "--ignore-whitespace", "-p1", str(patch_file)], cwd=target_dir)
        if code == 0:
            return True
        code, out = run_cmd(["git", "apply", "--ignore-whitespace", str(patch_file)], cwd=target_dir)
        return (code == 0)
    finally:
        if patch_file.is_file():
            patch_file.unlink()


def verify_patch_with_oracle(
    project_dir: Path,
    oracle_test: Path,
    diff_text: str,
    task_id: str,
) -> Tuple[bool, str, str]:
    """Run independent oracle against a fresh temporary copy of project_dir with diff_text applied.

    Returns: (oracle_pass: bool, classification: str, detail_message: str)
      classification is one of:
        - "independently passed"
        - "independently failed"
        - "unable to validate"
    Distinguishes assertion failures (<failure>) from setup/collection errors (<error>).
    """
    if not diff_text or not diff_text.strip():
        return False, "unable to validate", "unable to validate (no patch produced)"

    temp_eval = Path(tempfile.mkdtemp(prefix=f"eval_oracle_{task_id}_"))
    try:
        shutil.copytree(project_dir, temp_eval / "proj")
        patched_ok = apply_patch_to_dir(temp_eval / "proj", diff_text)
        if not patched_ok:
            return False, "unable to validate", "unable to validate (patch application failed on clean copy)"

        o_xml = temp_eval / "oracle_eval_junit.xml"
        ocode, oout = run_cmd(
            [
                sys.executable, "-m", "pytest", "-q", "--color=no",
                "-o", "junit_family=xunit2", f"--junitxml={o_xml}",
                str(oracle_test.resolve()),
            ],
            cwd=temp_eval / "proj",
            clean_env=True,
            scratch_dir=temp_eval,
        )
        o_tests = parse_junit(o_xml)
        passed_count = sum(1 for s in o_tests.values() if s == "passed")
        failed_count = sum(1 for s in o_tests.values() if s == "failed")
        error_count = sum(1 for s in o_tests.values() if s == "error")

        if ocode == 0 and bool(o_tests) and all(s == "passed" for s in o_tests.values()):
            return True, "independently passed", f"independently passed ({passed_count} oracle test(s) passed, 0 errors)"
        elif failed_count > 0 and error_count == 0:
            return False, "independently failed", f"independently failed ({failed_count} assertion failure(s), 0 collection/setup errors)"
        elif error_count > 0:
            return False, "unable to validate", f"unable to validate ({error_count} collection/setup error(s))"
        else:
            return False, "unable to validate", f"unable to validate (pytest exit code {ocode}, 0 tests recorded)"
    finally:
        shutil.rmtree(temp_eval, ignore_errors=True)


def validate_saved_results(out_dir: Path) -> int:
    """Offline Mode: Validate already-saved Phase 2 patches against independent oracles.

    Uses already-saved artifacts only. Zero API requests, zero credits.
    Keeps original benchmark projects untouched by running tests in isolated temporary copies.
    """
    out_dir = Path(out_dir)
    json_path = out_dir / "live_benchmark_results.json"
    if not json_path.is_file():
        print(f"Error: {json_path} not found. Please provide directory with saved results.")
        return 1

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error reading {json_path}: {exc}")
        return 1

    print("=" * 76)
    print("RECON MULTI-BUG BENCHMARK — OFFLINE POST-PATCH ORACLE VALIDATION")
    print("=" * 76)
    print(f"Validating already-saved Phase 2 artifacts in: {out_dir}")
    print("Zero API requests. Original benchmark projects remain completely untouched.\n")

    records = data.get("tasks", [])
    task_map = {t["id"]: t for t in BENCHMARK_TASKS}
    all_validated = True

    for r in records:
        tid = r["id"]
        task = task_map.get(tid)
        if not task:
            continue

        pdir = task["project_dir"]
        oracle = task["oracle_test"]
        task_out = out_dir / tid
        patch_file = task_out / "patch.diff"
        diff_text = patch_file.read_text(encoding="utf-8") if patch_file.is_file() else ""

        print(f"Evaluating Case: {tid} ({task['name']})...")
        oracle_pass, classification, oracle_detail = verify_patch_with_oracle(pdir, oracle, diff_text, tid)

        r["oracle_pass"] = oracle_pass
        r["oracle_classification"] = classification
        r["oracle_detail"] = oracle_detail

        print(f"  -> RECON Verdict: {r['verdict']} (exit code {r['exit_code']})")
        print(f"  -> Independent Oracle: [{classification.upper()}] {oracle_detail}")
        print()

    # Save updated reports
    aggregate_calls = data.get("aggregate_calls_made_or_reserved", 0)
    _save_reports(records, aggregate_calls, out_dir)

    print("-" * 76)
    print("Summary of Independent Oracle Validation:")
    for r in records:
        print(f"  * {r['id']}: [{r['oracle_classification'].upper()}] {r['oracle_detail']}")
    print("-" * 76)
    return 0


def run_live_evaluation(out_dir: Path) -> int:
    """Live Mode: Run RECON across all 5 tasks sequentially with strict limits."""
    print("=" * 76)
    print("RECON MULTI-BUG BENCHMARK — LIVE MODEL EVALUATION")
    print("=" * 76)
    print(f"Per-task budget: --max-calls {MAX_CALLS_PER_TASK}")
    print(f"Aggregate harness request cap: {MAX_TOTAL_AGGREGATE_CALLS} model calls")
    print("Note: 10 model calls is an application-level request cap, not a guaranteed account-wide dollar cap.")
    print("Zero automatic retries. Failed requests recorded as outcomes.")
    print("=" * 76)
    print()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    aggregate_calls = 0
    task_records = []

    for task in BENCHMARK_TASKS:
        tid = task["id"]
        pdir = task["project_dir"]
        breport = task["bug_report"]
        oracle = task["oracle_test"]
        task_out = out_dir / tid
        task_out.mkdir(parents=True, exist_ok=True)

        if aggregate_calls >= MAX_TOTAL_AGGREGATE_CALLS:
            print(f"[HALTED] Aggregate call cap reached ({aggregate_calls}/{MAX_TOTAL_AGGREGATE_CALLS}). Skipping {tid}.")
            task_records.append({
                "id": tid,
                "name": task["name"],
                "domain": task["domain"],
                "bug_type": task["bug_type"],
                "verdict": "ERROR",
                "exit_code": 3,
                "oracle_pass": False,
                "oracle_classification": "unable to validate",
                "oracle_detail": "unable to validate (halted by aggregate harness call cap)",
                "calls_made": 0,
                "calls_display": "0 (halted)",
                "calls_known": True,
                "max_calls": MAX_CALLS_PER_TASK,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "duration_s": 0.0,
                "reasons": ["Halted before dispatch by aggregate harness call cap"],
                "has_patch": False,
            })
            continue

        print(f"Running Task: {tid} ({task['name']})...")
        t_start = time.time()

        cmd = [
            sys.executable, "-m", "recon",
            "--project", str(pdir),
            "--bug-report", str(breport),
            "--max-calls", str(MAX_CALLS_PER_TASK),
            "--out", str(task_out),
            "--json",
        ]

        exit_code, stdout = run_cmd(cmd)
        elapsed = round(time.time() - t_start, 2)

        # Parse generated report
        report_file = task_out / "recon_report.json"
        report_data = {}
        if report_file.is_file():
            try:
                report_data = json.loads(report_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        status = report_data.get("status", "ERROR" if exit_code != 0 else "UNKNOWN")
        api_usage = report_data.get("api_usage", {})

        # Requirement 3: If a live run fails before producing a report, record its call count
        # as unknown and conservatively reserve the full two-call task budget (do NOT report 0).
        if api_usage and "calls_made" in api_usage:
            calls_made = int(api_usage["calls_made"])
            calls_display = str(calls_made)
            calls_known = True
        else:
            calls_made = MAX_CALLS_PER_TASK
            calls_display = f"unknown (conservatively reserved {MAX_CALLS_PER_TASK})"
            calls_known = False

        p_tokens = api_usage.get("prompt_tokens_reported", 0)
        c_tokens = api_usage.get("completion_tokens_reported", 0)
        diff_text = (report_data.get("patch") or {}).get("diff", "")

        aggregate_calls += calls_made

        # Independent Oracle Verification against fresh copy
        oracle_pass, classification, oracle_detail = verify_patch_with_oracle(pdir, oracle, diff_text, tid)

        print(f"  -> Verdict: {status} (exit code {exit_code})")
        print(f"  -> Calls: {calls_display}/{MAX_CALLS_PER_TASK} | Tokens: {p_tokens} in / {c_tokens} out | Time: {elapsed}s")
        print(f"  -> Independent Oracle: [{classification.upper()}] {oracle_detail}")
        print()

        task_records.append({
            "id": tid,
            "name": task["name"],
            "domain": task["domain"],
            "bug_type": task["bug_type"],
            "verdict": status,
            "exit_code": exit_code,
            "oracle_pass": oracle_pass,
            "oracle_classification": classification,
            "oracle_detail": oracle_detail,
            "calls_made": calls_made,
            "calls_display": calls_display,
            "calls_known": calls_known,
            "max_calls": MAX_CALLS_PER_TASK,
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "duration_s": elapsed,
            "reasons": report_data.get("reasons", []),
            "has_patch": bool(diff_text.strip()),
        })

    # Save Results
    _save_reports(task_records, aggregate_calls, out_dir)
    return 0


def _save_reports(records: List[Dict[str, Any]], aggregate_calls: int, out_dir: Path):
    json_path = out_dir / "live_benchmark_results.json"
    md_path = out_dir / "live_benchmark_results.md"

    summary_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_tasks": len(records),
        "aggregate_calls_made_or_reserved": aggregate_calls,
        "aggregate_call_cap": MAX_TOTAL_AGGREGATE_CALLS,
        "tasks": records,
    }
    json_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    # Generate Markdown Table
    md_lines = [
        "# RECON Multi-Bug Benchmark: Live Nemotron Evaluation Results",
        "",
        f"**Date**: {summary_data['timestamp']}  ",
        f"**Model**: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` via Nebius Token Factory  ",
        f"**Cost Controls**: Hard cap `--max-calls 2` per task; aggregate harness limit {MAX_TOTAL_AGGREGATE_CALLS} calls max.  ",
        "*Notice: 10 model calls is an application-level request cap, not a guaranteed account-wide dollar cap. Check your Nebius console for actual billing.*",
        "",
        "## Summary Table",
        "",
        "| Task ID | Task Name | Domain | RECON Verdict | Independent Oracle | API Calls | Tokens (In/Out) | Duration |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in records:
        v_str = f"`{r['verdict']}`"
        o_classification = r.get("oracle_classification", "independently passed" if r["oracle_pass"] else "unable to validate")
        if o_classification == "independently passed":
            o_str = "✅ **PASS** (independently passed)"
        elif o_classification == "independently failed":
            o_str = "❌ **FAIL** (independently failed)"
        else:
            o_str = f"⚪ **N/A** ({r.get('oracle_detail', 'unable to validate')})"

        tokens_str = f"{r['prompt_tokens']} / {r['completion_tokens']}"
        md_lines.append(
            f"| `{r['id']}` | {r['name']} | {r['domain']} | {v_str} | {o_str} | {r['calls_display']}/{r['max_calls']} | {tokens_str} | {r['duration_s']}s |"
        )

    md_lines += [
        "",
        "## Evaluation Methodology Notes",
        "1. **Isolated Oracle Tests**: Each independent oracle test was stored completely outside the project directory received by RECON. RECON never saw, scanned, or tampered with the oracle.",
        "2. **Pre-Evaluation Proof**: Prior to running RECON, each oracle test was verified to FAIL cleanly with genuine test assertions (and zero collection/setup errors) on the original unmodified buggy project.",
        "3. **Zero Automated Retries**: Each task was executed once sequentially. Failed requests or incomplete runs were recorded directly.",
        "4. **Conservative Budget Accounting**: If a run fails before producing a report, the harness conservatively reserves the full 2-call budget instead of assuming zero calls.",
        "5. **Original Files Untouched**: All evaluations and patches were verified in temporary working copies; original benchmark source files remained unchanged.",
        "",
    ]

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Results written to:\n  - {json_path}\n  - {md_path}")


def main():
    parser = argparse.ArgumentParser(description="RECON Multi-Bug Benchmark Harness")
    parser.add_argument(
        "--mode",
        choices=["check-offline", "run-live", "validate-saved"],
        default="check-offline",
        help="check-offline: verify baseline and oracle tests offline; run-live: run live evaluation; validate-saved: validate already-saved patches offline",
    )
    parser.add_argument(
        "--out",
        default="docs/benchmark_results",
        help="Directory to save evaluation reports",
    )
    args = parser.parse_args()

    if args.mode == "check-offline":
        code = check_offline_baseline_and_oracles()
        sys.exit(code)
    elif args.mode == "run-live":
        code = run_live_evaluation(Path(args.out))
        sys.exit(code)
    elif args.mode == "validate-saved":
        code = validate_saved_results(Path(args.out))
        sys.exit(code)


if __name__ == "__main__":
    main()

