"""Command-line entry point:  python -m recon --project DIR --bug-report FILE"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .agent import DISCLAIMER, run_recon
from .config import Config, ConfigError, load_dotenv
from .llm import FixtureLLM, LLMClient
from .verify import COULD_NOT_REPRODUCE, ERROR, UNVERIFIED, VERIFIED

EXIT_CODES = {VERIFIED: 0, UNVERIFIED: 1, COULD_NOT_REPRODUCE: 2, ERROR: 3}
MAX_BUG_CHARS = 8000


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recon", description="RECON: verification-first Python bug-fixing agent.")
    p.add_argument("--project", help="path to the Python project (never modified)")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--bug-report", help="path to a text/markdown bug report")
    src.add_argument("--bug", help="bug report as a string")
    p.add_argument("--offline-fixtures", help="replay canned model responses from this directory (no API, no credits)")
    p.add_argument("--out", default="recon_output", help="where to write the JSON report, test and diff")
    p.add_argument("--max-calls", type=int, help="override RECON_MAX_API_CALLS for this run")
    p.add_argument("--json", action="store_true", help="also print the full JSON report to stdout")
    p.add_argument("--check-config", action="store_true", help="show which settings are present (no API call) and exit")
    return p


def check_config(cfg: Config) -> int:
    def flag(v: str) -> str:
        return "set" if v else "MISSING"
    print("RECON configuration (values are never printed):")
    print(f"  NEBIUS_API_KEY  : {flag(cfg.api_key)}")
    print(f"  NEBIUS_BASE_URL : {flag(cfg.base_url)}")
    print(f"  NEBIUS_MODEL    : {flag(cfg.model)}")
    print(f"  call budget={cfg.max_api_calls}  max_output_tokens={cfg.max_output_tokens}  "
          f"context_chars={cfg.max_context_chars}  http_timeout={cfg.http_timeout}s  "
          f"test_timeout={cfg.test_timeout}s  repeats={cfg.repeats}")
    missing = cfg.missing_api_settings()
    print("  API mode ready." if not missing else f"  API mode NOT ready (missing: {', '.join(missing)}). Offline mode still works.")
    return 0 if not missing else 3


def render_summary(report: dict) -> str:
    lines = ["", "=" * 64, f" RECON RESULT: {report['status']}", "=" * 64]
    for r in report.get("reasons", []):
        lines.append(f" - {r}")
    base = report.get("baseline", {}).get("repro_runs", [])
    if base:
        lines.append(f" baseline repro test : {', '.join(r['outcome'] for r in base)} (expected FAILED)")
    post = report.get("post_patch", {}).get("post_repro_runs", [])
    if post:
        lines.append(f" post-patch repro    : {', '.join(r['outcome'] for r in post)} (expected PASSED)")
    ex = (report.get("post_patch") or {}).get("post_existing")
    if ex:
        lines.append(f" existing tests after: {ex['outcome']} {ex['counts']}")
    if report["patch"].get("changed_files"):
        lines.append(f" changed files       : {', '.join(report['patch']['changed_files'])}")
    u = report.get("api_usage", {})
    lines.append(f" API calls           : {u.get('calls_made', 0)}/{u.get('max_calls_budget', 0)} "
                 f"(tokens reported: {u.get('prompt_tokens_reported', 0)} in / {u.get('completion_tokens_reported', 0)} out)")
    if report["patch"].get("diff"):
        lines += ["", "--- proposed patch (applied ONLY to a temp copy; your files are untouched) ---",
                  report["patch"]["diff"].rstrip()]
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()
    try:
        cfg = Config.from_env().with_max_calls(args.max_calls)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 3
    if args.check_config:
        return check_config(cfg)
    if not args.project:
        print("error: --project is required", file=sys.stderr)
        return 3
    if args.bug_report:
        try:
            bug = Path(args.bug_report).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Cannot read bug report: {exc}", file=sys.stderr)
            return 3
    elif args.bug:
        bug = args.bug
    else:
        print("error: provide --bug-report FILE or --bug TEXT", file=sys.stderr)
        return 3
    bug = bug.strip()
    if not bug:
        print("error: bug report is empty", file=sys.stderr)
        return 3
    if len(bug) > MAX_BUG_CHARS:
        bug = bug[:MAX_BUG_CHARS] + "\n[truncated by RECON]"

    if args.offline_fixtures:
        fx = Path(args.offline_fixtures)
        if not (fx / "repro_test.txt").is_file() or not (fx / "patch.json").is_file():
            print("Offline fixtures dir must contain repro_test.txt and patch.json", file=sys.stderr)
            return 3
        llm: LLMClient = FixtureLLM(fx)
        print("[offline mode] replaying canned model responses; no network, no credits used.")
    else:
        missing = cfg.missing_api_settings()
        if missing:
            print("Missing environment variables: " + ", ".join(missing) +
                  "\nSee .env.example, or try the credit-free demo with --offline-fixtures.", file=sys.stderr)
            return 3
        llm = LLMClient(cfg)

    report = run_recon(Path(args.project), bug, cfg, llm, Path(args.out))
    print(render_summary(report))
    print(f"\nReport written to {Path(args.out) / 'recon_report.json'}")
    if args.json:
        print(json.dumps(report, indent=2))
    return EXIT_CODES.get(report["status"], 3)
