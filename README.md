---
title: RECON Bug Fixing Agent
emoji: 🛡️
colorFrom: green
colorTo: gray
sdk: gradio
sdk_version: 6.30.0
app_file: app.py
pinned: false
license: mit
---

<p align="center">
  <img src="docs/recon_wordmark.svg" alt="RECON Logo" width="620">
</p>

<p align="center">
  <img src="docs/recon_dashboard.png" alt="RECON Terminal Verification Dashboard" width="820">
</p>

# RECON — verification-first autonomous bug fixing

RECON takes a Python bug report and a local project, then **reproduces the bug with a generated pytest test, patches the code in a temporary copy, and decides the outcome from real test results** — never from the model's claim.

> **Passing tests are evidence of a fix, not mathematical proof of correctness.**

---

### Nebius × NVIDIA Global AI Hackathon Summary

* **Runtime Platform**: **Nebius Token Factory** (OpenAI-compatible inference endpoint at `https://api.tokenfactory.nebius.com/v1/`).
* **NVIDIA Open Model**: **`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`** (tested and verified live against the pricing bug demo).
* **Open Source License**: **MIT License** (OSI-approved, included in [`LICENSE`](LICENSE) and recognized in the GitHub repository About section).
* **Project Timeline**: Conceived, built, tested, and published during the official hackathon submission window (August 26, 2026 – October 30, 2026; initial commit on October 22, 2026).
* **Verification Philosophy**: AI coding agents routinely declare "fixed it!" without proof. RECON enforces automated empirical verification by running real pytest suites inside isolated temporary workspaces with an application-level hard ceiling of at most 2 model calls (`--max-calls 2`).

---

## Verdict Statuses

| Status | Meaning (computed by Python in `recon/verify.py`) |
|---|---|
| `VERIFIED` | The repro test **failed** on the unmodified code (every baseline run), **passes** after the patch (every rerun), no protected file was touched, and no previously-passing existing test regressed. |
| `UNVERIFIED` | A patch was produced but at least one requirement failed (still failing, regression, rejected patch, tampering, flaky). |
| `COULD NOT REPRODUCE` | The generated test did not fail cleanly on the original code (it passed, timed out, or errored). No patch call is spent. |
| `ERROR` | Operational problem (missing config, API error, budget exhausted, bad project). Not a verification verdict. |

---

## How it works

```
bug report + project
   │  copy safe files to a temp dir (no .git/venv/secrets/symlinks/huge files)
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

Your original files are **never modified**; all edits and tests execute in a clean temporary copy. The patch is reported as a unified diff.

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

RECON includes a standalone local terminal-styled web application with live animated pipeline steppers:

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

Sample outputs are archived in `docs/sample_output_verified.txt`, `docs/sample_output_unverified.txt`, and `docs/sample_report_verified.json`.

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

6. Execute the live run capped at 2 model requests:
```bash
python -m recon --project examples/buggy_shop --bug-report examples/buggy_shop/bug_report.md --max-calls 2
```

Outputs land in `recon_output/`:
* `recon_report.json` — Complete JSON execution audit including token usage and checks.
* `test_recon_repro.py` — The generated reproduction test (AST-scanned).
* `patch.diff` — The generated unified patch.

Exit codes: `0` VERIFIED, `1` UNVERIFIED, `2` COULD NOT REPRODUCE, `3` ERROR.

---

## Cost Controls & Application-Level Limits

* **Call Budget** (`--max-calls 2` or `RECON_MAX_API_CALLS`): Limits this run to at most two model requests (one for reproduction, one for patch). Requests are counted *before* dispatching.
* **Token Controls**: `max_tokens` (`RECON_MAX_OUTPUT_TOKENS`, default 1500) is enforced per request; input is capped by `RECON_MAX_CONTEXT_CHARS` (~4 chars ≈ 1 token).
* **No Runaway Loops**: Explicit HTTP timeouts, **zero automatic retries**, and zero autonomous agent loops. Test verdicts are computed by deterministic Python logic, never by model claims.
* *Notice*: These are application-level request controls, not a hard account-wide billing cap. Check your Nebius console for real account usage.

---

## Security Model and Limitations

* **Local Execution**: The generated test and patched code run locally via pytest in a clean temporary copy.
* **AST Safety Scans**: Generated test code is inspected before execution to block dangerous imports or calls (`os`, `sys`, `subprocess`, `urllib`, `socket`, `open`, `eval`, `exec`).
* **Test Protection**: Patches cannot touch test files, `conftest.py`, or pytest configuration. All test files are SHA-256 hashed before and after patching to detect tampering.
* **Environment Scrubbing**: API keys (`NEBIUS_API_KEY`, etc.) are explicitly scrubbed from the pytest subprocess environment so untrusted code cannot read them.
* **Empirical Evidence**: Passing tests demonstrate that the reproduction test was resolved and existing tests did not regress. They are empirical evidence, not a mathematical proof of correctness.

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
