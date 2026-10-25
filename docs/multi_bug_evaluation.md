# RECON Multi-Bug Evaluation Report

This document records the empirical results of evaluating RECON across five distinct, controlled Python/pytest benchmark bugs using **`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`** via **Nebius Token Factory**.

> **Methodology Note**: These are five small, curated examples designed to test RECON's verification loop across different bug archetypes under strict cost and call controls. Passing tests are empirical evidence that the reproduction test was resolved and existing tests did not regress; they are **not a mathematical proof of correctness**, nor do these five cases represent a general statistical reliability or success-rate claim across arbitrary Python repositories.

---

## Evaluation Summary

* **Date**: October 25, 2026
* **Model**: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (OpenAI-compatible inference via Nebius Token Factory)
* **Execution Mode**: Single sequential pass; zero automated retries.
* **Per-Task Budget**: Hard cap of at most 2 model calls (`--max-calls 2`).
* **Harness Cap**: Strict aggregate limit of 10 model requests maximum across all 5 tasks.
* **Total API Calls Used**: **9 requests** (within the 10-call aggregate cap).
* **Reported Token Usage**: **6,814 prompt tokens** and **5,218 completion tokens** across completed requests (excluding `03_token_bucket`, where exact token consumption is unavailable because the request was cut off by output token limits before returning a usage payload).
* **Overall Outcome**:
  * **3 / 5 cases** were **VERIFIED** by RECON and **independently passed** ground-truth oracle tests on clean copies.
  * **2 / 5 cases** halted safely with **ERROR** before producing a patch (1 due to token truncation, 1 due to empty model response).

---

## Benchmark Results Table

| Task ID | Benchmark Name | Domain & Verified Bug Archetype | RECON Verdict | Independent Oracle | API Calls | Reported Tokens (In / Out) | Duration |
|---|---|---|---|---|---|---|---|
| `01_buggy_shop` | Pricing Bulk Threshold | Pricing & Billing: boundary check (`>` vs `>=`) | `VERIFIED` | ✅ **PASS** (independently passed) | 2 / 2 | 1,724 / 1,576 | 12.5s |
| `02_semver` | Semantic Version Comparison | Developer Tooling: string vs integer sorting (`"10"` vs `"9"`) | `VERIFIED` | ✅ **PASS** (independently passed) | 2 / 2 | 2,009 / 1,242 | 11.7s |
| `03_token_bucket` | Token Bucket Rate Limiter | Systems & Networking: unbounded idle token accumulation (missing capacity clamp) | `ERROR` | ⚪ **N/A** (no patch produced) | 1 / 2 | *Unavailable (truncated)* | 8.0s |
| `04_slugify` | URL Slug Truncation Formatter | Web & Text: trailing delimiter leak (`max_len=12`) | `ERROR` | ⚪ **N/A** (no patch produced) | 2 / 2 | 712 / 821 | 15.0s |
| `05_tax_calc` | Progressive Tax Calculator | Finance & Payroll: non-marginal tier bracket math | `VERIFIED` | ✅ **PASS** (independently passed) | 2 / 2 | 2,369 / 1,579 | 11.2s |

---

## Detailed Case Findings

### 1. `01_buggy_shop` (Pricing Bulk Threshold) — `VERIFIED`
* **Bug**: `line_total(unit_price, quantity)` applied a 10% discount only when `quantity > 10` instead of `quantity >= 10`. Orders of exactly 10 units were billed without a discount.
* **RECON Workflow**:
  * Call 1 generated an AST-safe pytest reproduction test asserting `line_total(10.0, 10) == 90.0`, which failed cleanly with an assertion error (`assert 100.0 == 90.0`) on unmodified code.
  * Call 2 generated a unified diff changing `if quantity > BULK_THRESHOLD:` to `if quantity >= BULK_THRESHOLD:`.
  * RECON verified the repro test passed, all 4 baseline tests passed, and test file hashes were unmodified.
* **Independent Oracle**: Applied the patch to a fresh, clean project copy. The independent oracle test passed (2/2 tests passed, 0 failures, 0 errors).

### 2. `02_semver` (Semantic Version Comparison) — `VERIFIED`
* **Bug**: Semver tuple parser left components as strings (`tuple(parts)`), causing lexicographical string comparison where `"1.10.0"` was evaluated as older than `"1.9.0"` because `"10" < "9"`.
* **RECON Workflow**:
  * Call 1 generated a reproduction test asserting `compare("1.10.0", "1.9.0") > 0`, cleanly reproducing the bug.
  * Call 2 generated a patch converting components to integers: `tuple(int(p) for p in parts)`.
  * RECON verified the repro test and all baseline tests passed.
* **Independent Oracle**: Applied to a clean copy; all 3 independent oracle test cases passed (0 failures, 0 errors).

### 3. `03_token_bucket` (Token Bucket Rate Limiter) — `ERROR`
* **Bug**: `TokenBucket.refill(current_time)` accumulated refilled tokens indefinitely (`self.tokens += elapsed * self.refill_rate`) without clamping to `self.capacity`. After idle periods, bursts far exceeding bucket capacity were permitted.
* **Execution & Safety Halt**:
  * During Call 1 (reproduction test generation), the model's completion exceeded the per-request token limit (`RECON_MAX_OUTPUT_TOKENS=1500`) while constructing a multi-threaded test harness.
  * RECON detected the truncation and aborted immediately with exit code 3 (`ERROR: model output was cut off by max_tokens`).
  * **Cost Control in Action**: Only **1 call** was spent. RECON avoided infinite retry loops and did not attempt an invalid patch.
  * **Token Usage Note**: Because the HTTP response ended abruptly at the token ceiling, no client usage payload was returned; exact token consumption for this single call is unavailable.
* **Independent Oracle**: N/A (no patch produced).

### 4. `04_slugify` (URL Slug Truncation Formatter) — `ERROR`
* **Bug**: `slugify("quick brown fox jumps", max_len=12)` produced `"quick-brown-"` with a trailing hyphen instead of stripping trailing delimiters.
* **Execution & Safety Halt**:
  * Call 1 generated a valid reproduction test confirming the trailing hyphen issue.
  * In Call 2 (patch generation), the model returned an empty completion payload.
  * RECON caught the empty response, rejected the empty patch, and halted with exit code 3 (`ERROR: model returned empty content`).
  * Total calls: 2 (712 prompt tokens, 821 completion tokens).
* **Independent Oracle**: N/A (no patch produced).

### 5. `05_tax_calc` (Progressive Tax Calculator) — `VERIFIED`
* **Bug**: Progressive tax calculator computed tier 3 tax as `(income - 10000) * 0.20` instead of `(income - 50000) * 0.20`, taxing non-marginal income at the higher rate.
* **RECON Workflow**:
  * Call 1 generated a reproduction test asserting `calculate_tax(60000) == 6000.0`, reproducing the mathematical error (`14000.0 != 6000.0`).
  * Call 2 patched the formula to `tier3_tax = (income - 50000) * 0.20`.
  * RECON verified that both the reproduction test and baseline existing tests passed cleanly.
* **Independent Oracle**: Applied to a clean copy; all 3 independent oracle test cases passed (0 failures, 0 errors).

---

## Safety, Privacy & Methodology Principles

1. **Independent Ground Truth Oracles**: Every oracle test was kept in `examples/eval_benchmarks/oracles/`, outside the project directory received by RECON. RECON never saw, scanned, or modified the oracles.
2. **Pre-Patch Failure Proof**: Before any patch was generated, each oracle was verified to fail cleanly with actual test assertion failures (0 setup/collection errors) on the original unmodified buggy project.
3. **No Project Contamination**: All patches were verified in ephemeral temporary directories; original benchmark project files remained untouched.
4. **Credential Scrubbing**: Subprocess environments were scrubbed of `NEBIUS_API_KEY` and other sensitive variables.
5. **Privacy Cleanliness**: No machine-local file paths, personal usernames, or secret tokens are tracked or published.

---

## Execution & Safety Accounting

* **Live Model Evaluation**: The live Nemotron evaluation ran against the Nebius Token Factory inference API using a total of **9 API requests** (within the 10-call aggregate cap) and consumed a reported **6,814 prompt tokens** and **5,218 completion tokens** across completed requests.
* **Offline Post-Run Oracle Validation**: The subsequent independent oracle validation on the saved patch artifacts was conducted **strictly offline** in isolated temporary directories. It made **zero additional API requests** and spent **no additional API credits**.

