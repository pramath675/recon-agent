<p align="center">
  <img src="docs/recon_wordmark.svg" alt="RECON Logo" width="620">
</p>

<p align="center">
  <img src="docs/recon_dashboard.png" alt="RECON Terminal Verification Dashboard" width="820">
</p>

# RECON — verification-first autonomous bug fixing

RECON takes a Python bug report and a local project, then **reproduces the bug with a generated pytest test, patches the code in a temporary working copy, and decides the outcome from real test results** — never from the model's claim.

> **Passing tests are evidence of a fix, not mathematical proof of correctness.**

---

### Nebius × NVIDIA Global AI Hackathon Summary

* **Runtime Platform**: **Nebius Token Factory** (OpenAI-compatible inference endpoint at `https://api.tokenfactory.nebius.com/v1/`).
* **NVIDIA Open Model**: **`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`** (used in one observed live CLI run on the pricing bug demo).
* **Demo Video**: **[YouTube Walkthrough (2 min)](https://youtu.be/ENAKW9ItM0o)**
* **Open Source License**: **MIT License** (OSI-approved, included in [`LICENSE`](LICENSE) and recognized in the GitHub repository About section).
* **Project Timeline**: Conceived, built, tested, and published during the official hackathon submission window (August 26, 2026 – October 30, 2026; initial commit on October 22, 2026).
* **Verification Philosophy**: AI coding agents routinely declare "fixed it!" without proof. RECON enforces automated empirical verification by running real pytest suites inside a temporary working copy.
* **Cost Controls**: The default application budget is 4 calls (`RECON_MAX_API_CALLS=4`), permitting up to one repair attempt per stage, while `--max-calls 2` is an optional cap that limits the run to at most two model calls. In the no-repair path under that cap, these are one reproduction call and one patch call. A repair call may consume the remaining budget and prevent a later stage.

---

## Verdict Statuses & Exit Codes

| Status | Exit Code | Meaning (computed by Python in `recon/verify.py` & `recon/cli.py`) |
|---|---|---|
| `VERIFIED` | `0` | The repro test **failed** on the unmodified code (every baseline run), **passes** after the patch (every rerun), no protected file was touched, and no previously-passing existing test regressed. |
| `UNVERIFIED` | `1` | A patch was produced but at least one requirement failed (still failing, regression, rejected patch, tampering, flaky). |
| `COULD NOT REPRODUCE` | `2` | The repro test could not be made to fail cleanly after at most one repair attempt. RECON stops before generating a patch. |
| `ERROR` | `3` | Operational problem (missing config, API error, budget exhausted, invalid project). Not a verification verdict. |

---

## How it works

RECON's CLI accepts a local Python project and a bug report. It runs a four-stage workflow:
- **Baseline**: Run the project's existing tests in a temporary working copy.
- **Reproduce**: Generate a pytest test that should fail on the original code. If it cannot be made to fail cleanly after at most one repair attempt, RECON stops with `COULD NOT REPRODUCE` before generating a patch.
- **Patch**: Generate structured search-and-replace edits and apply them to a temporary working copy.
- **Verify**: Run the reproduction test and existing tests again.

```
bug report + project
   │  copy safe files to a temporary working copy (no .git/venv/secrets/symlinks/huge files)
   ▼
run existing tests (baseline)
   ▼
MODEL CALL 1 → reproduction test ──► AST safety scan ──► run on original code (x RECON_REPEATS)
   │                                   must FAIL cleanly, else ONE repair call, else COULD NOT REPRODUCE
   ▼
MODEL CALL 2 → search/replace edits ──► validate paths/syntax ──► apply to a SECOND temp copy
   │                                     patches cannot touch tests or conftest.py
   ▼
rerun repro test (x RECON_REPEATS) + existing tests + hash-check every test/config file
   ▼
verify.evaluate() → status      (one repair call allowed if not VERIFIED)
```

Your original files are **never modified**; all edits and tests execute in a clean temporary working copy. The patch is reported as a unified diff.

---

## Install

**Linux / macOS**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Windows PowerShell**
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
```

Python 3.9+ required; the only direct runtime dependency is `pytest` (and `gradio` for the web dashboard).

---

## Run the unit tests (no API, zero credits)

```bash
python -m pytest
```

---

## Interactive Web Dashboard (Gradio)

* **Public Interactive Demo**: **[https://recon-agent-frbn.onrender.com](https://recon-agent-frbn.onrender.com)** *(Hosted on Render Free Tier, offline fixtures only; subject to a possible wake-up delay if spun down from inactivity)*

You can also run the web dashboard locally:

```bash
python app.py
```
Open **`http://127.0.0.1:7860/`** in your browser.
* **▶ Run Good Fixture (Expected: VERIFIED)**: Steps through baseline, repro, patch, and verify stages to produce a verified unified diff.
* **▶ Run Bad Fixture (Expected: UNVERIFIED)**: Executes a flawed patch, catches the regression on existing tests, and flags `REGRESSION DETECTED`.
* *Offline execution*: The web UI runs entirely on local fixtures with zero external API calls or secret keys required.

---

## Demo 1 — CLI Offline Fixture Runs (Zero Credits)

Replays canned model responses through the **real** verification pipeline (real pytest subprocesses, real AST scans, real SHA-256 hash checks).

```bash
# Good fix -> VERIFIED (exit code 0)
python -m recon --project examples/buggy_shop --bug-report examples/buggy_shop/bug_report.md --offline-fixtures examples/fixtures/good

# Bad fix -> UNVERIFIED with regression flagged (exit code 1)
python -m recon --project examples/buggy_shop --bug-report examples/buggy_shop/bug_report.md --offline-fixtures examples/fixtures/bad
```

Sample outputs reflecting these offline fixture runs on the bundled `buggy_shop` example are archived in `docs/sample_output_verified.txt`, `docs/sample_output_unverified.txt`, and `docs/sample_report_verified.json`.

---

## Demo 2 — Live Run with Nebius Token Factory & NVIDIA Model

To run against a live NVIDIA model on Nebius Token Factory:

1. Create an account and an **API key** in the [Nebius Token Factory console](https://tokenfactory.nebius.com/).
2. Select an **NVIDIA open model** (e.g., `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`).
3. Copy the **OpenAI-compatible base URL** (`https://api.tokenfactory.nebius.com/v1/`).
4. Configure your `.env` file (which is ignored by Git and never committed):
```bash
cp .env.example .env        # Windows: Copy-Item .env.example .env
# Edit .env:
# NEBIUS_API_KEY=your-actual-api-key
# NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
# NEBIUS_MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
```
5. Safely verify configuration without leaking credentials to the screen:
```bash
python -m recon --check-config
```
*(Prints `set` or `MISSING`; secret values are never printed).*

6. Execute the live run:
```bash
# Default execution (allows up to 4 calls to support repair attempts):
python -m recon --project examples/buggy_shop --bug-report examples/buggy_shop/bug_report.md

# Or with an optional two-call cap (limits the entire run to at most two model calls):
python -m recon --project examples/buggy_shop --bug-report examples/buggy_shop/bug_report.md --max-calls 2
```

Outputs land in `recon_output/`:
* `recon_report.json` — Complete JSON execution audit including token usage and checks.
* `test_recon_repro.py` — The generated reproduction test (AST-scanned).
* `patch.diff` — The generated unified patch.

Exit codes: `0` VERIFIED, `1` UNVERIFIED, `2` COULD NOT REPRODUCE, `3` ERROR.

---

## Cost Controls & Application-Level Limits

* **Call Budget** (`RECON_MAX_API_CALLS`, default 4, or optional `--max-calls` cap):
  - The default budget is **4 calls** across the pipeline (`RECON_MAX_API_CALLS=4`), supporting up to one repair attempt per stage (initial repro + repro repair, and initial patch + patch repair). Early termination (such as `COULD NOT REPRODUCE`) stops the run early and uses fewer calls.
  - `--max-calls 2` is an optional cap that limits the run to at most two model calls. In the no-repair path under that cap, these are one reproduction call and one patch call. A repair call may consume the remaining budget and prevent a later stage.
  - Calls are counted *before* dispatching, so failed requests still consume budget.
* **Token Controls**: `max_tokens` (`RECON_MAX_OUTPUT_TOKENS`, default 1500) is enforced per request; input is capped by `RECON_MAX_CONTEXT_CHARS` (~4 chars ≈ 1 token).
* **Early Exit**: Generate a pytest test that should fail on the original code. If it cannot be made to fail cleanly after at most one repair attempt, RECON stops with `COULD NOT REPRODUCE` before generating a patch.
* **No Runaway Loops**: Explicit HTTP timeouts, zero autonomous agent loops, and at most one bounded retry strictly for empty model responses when budget remains (zero retries for generic errors, timeouts, or truncated responses). Test verdicts are computed by deterministic Python logic, never by model claims.
* *Notice*: These are application-level request controls, not a hard account-wide billing cap. Check your Nebius console for real account usage.

---

## Security Model and Limitations

* **Temporary Working Copy**: All edits and tests execute in a temporary working copy; original project files are never modified.
* **No OS-Level Sandbox**: RECON executes pytest locally in a temporary working copy with a scrubbed environment (`NEBIUS_API_KEY` and other sensitive variables stripped), temporary `HOME`, timeouts, and process limits. **RECON does NOT provide OS-level network or filesystem isolation.** For untrusted repositories, execute RECON inside a container or virtual machine.
* **AST Safety Scans**: Generated test code is inspected before execution to block dangerous imports or calls (`os`, `sys`, `subprocess`, `urllib`, `socket`, `open`, `eval`, `exec`).
* **Test Protection & Integrity**: Patches cannot touch test files, `conftest.py`, or pytest configuration. All test files are SHA-256 hashed before and after patching to detect tampering.
* **Environment Scrubbing**: API keys (`NEBIUS_API_KEY`, etc.) are explicitly scrubbed from the pytest subprocess environment so untrusted code cannot read them.
* **Empirical Evidence**: Passing tests demonstrate that the reproduction test was resolved and existing tests did not regress. They are empirical evidence, not a mathematical proof of correctness.
* **Test Breadth & Future Work**: RECON was initially developed on the bundled `examples/buggy_shop` demo and subsequently evaluated on a five-case benchmark suite comprising a repeat of the original demo bug plus four additional bug cases ([`docs/multi_bug_evaluation.md`](docs/multi_bug_evaluation.md)). Evaluating RECON across large external repositories and broader bug benchmarks remains future work.
* **Human Review**: The reproduction test is LLM-generated; a human developer should review the test and the unified diff before trusting the result.

---

## Multi-Bug Live Evaluation (Nemotron 3 Nano on Nebius Token Factory)

To evaluate whether RECON's verification loop functions consistently across multiple scenarios, we conducted a capped live evaluation across a five-case benchmark suite using `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` via Nebius Token Factory. The benchmark suite comprises a repeat of the bundled `01_buggy_shop` pricing demo bug plus four additional Python/pytest benchmark bugs:

| Task ID | Benchmark Case | Domain & Bug Archetype | RECON Verdict | Independent Oracle | API Calls | Reported Tokens (In / Out) |
|---|---|---|---|---|---|---|
| `01_buggy_shop` | Pricing Bulk Threshold (repeat of demo) | Pricing & Billing: boundary check (`>` vs `>=`; repeats demo bug) | `VERIFIED` | ✅ **PASS** | 2 / 2 | 1,724 / 1,576 |
| `02_semver` | Semantic Version Sorting | Developer Tooling: string vs integer sorting (`"10"` vs `"9"`) | `VERIFIED` | ✅ **PASS** | 2 / 2 | 2,009 / 1,242 |
| `03_token_bucket` | Token Bucket Rate Limiter | Systems & Networking: unbounded idle token accumulation (missing capacity clamp) | `ERROR` | ⚪ **N/A** (no patch) | 1 / 2 | *Unavailable (truncated)* |
| `04_slugify` | URL Slug Formatter | Web & Text: trailing delimiter leak (`max_len=12`) | `ERROR` | ⚪ **N/A** (no patch) | 2 / 2 | 712 / 821 |
| `05_tax_calc` | Progressive Tax Calculator | Finance & Payroll: non-marginal tier bracket math | `VERIFIED` | ✅ **PASS** | 2 / 2 | 2,369 / 1,579 |

* **Empirical Outcomes**: Overall, **3/5 cases were VERIFIED** (including the repeated `01_buggy_shop` demo case) and independently passed external ground-truth oracles on clean project copies. Among the **four additional cases**, **2 were VERIFIED** (`02_semver`, `05_tax_calc`) and **2 safely halted in ERROR** before generating a patch: `03_token_bucket` cleanly aborted when reproduction test construction reached the `max_tokens=1500` output ceiling, and `04_slugify` cleanly aborted when the model returned an empty patch payload.
* **Cost & Safety Controls**: The live evaluation used **9 API requests** total (strictly within the 10-call aggregate cap). Aggregate **reported token usage** across completed requests was **6,814 prompt tokens** and **5,218 completion tokens** (excluding `03_token_bucket`, whose truncated request did not return a usage payload; exact consumption for that call is unavailable). The evaluation ran sequentially with zero automatic retries.
* **Scope & Methodology**: These results reflect five small, curated benchmark examples (one repeated demo bug and four additional cases) evaluated under strict two-call caps, not a broad statistical reliability or success-rate claim. Passing tests remain empirical evidence of a fix rather than proof of correctness. See [`docs/multi_bug_evaluation.md`](docs/multi_bug_evaluation.md) for detailed case breakdowns and methodology notes.

---

## Repository Layout

```
recon/                Core agent engine (cli, agent, llm, runner, verify, patching, safety, config)
tests/                Unit, safety, and end-to-end integration tests
examples/buggy_shop/  Demo project with deliberate off-by-one bulk discount bug
examples/fixtures/    Canned model responses (good / bad) for credit-free testing
docs/                 Branding wordmark, dashboard screenshot, and sample run reports
app.py                Interactive Gradio terminal web dashboard
```
