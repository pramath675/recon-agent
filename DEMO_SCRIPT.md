# RECON Demo Video Walkthrough Script & Subtitles (~2 min 52 sec)

> **Accuracy Notice**: This video demonstrates RECON's verification engine using bundled offline fixtures. It does **not** depict a live CLI run.
>
> * **Hosted Browser Demo (Render)**: Runs entirely on bundled offline fixtures with zero live model calls and no API keys required.
> * **Live CLI**: Connects to `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` on Nebius Token Factory using the user's own API key and account credits.

---

## 1. Timeline & Spoken Narration

### [0:00 – 0:18] Scene 1: The Core Problem & Verification Principle
* **Visual**: RECON terminal dashboard (idle state); tagline "Verification-First Autonomous Bug Fixing Agent". Render Free tier hosting notice and offline execution notice visible at the footer.
* **Audio / Spoken Narration**:
  > "Most AI coding agents say 'fixed it!' and move on. RECON does not take their word for it. It is a verification-first bug fixing agent that only reports VERIFIED when independent pytest runs prove the bug existed and was completely resolved without regressions."

### [0:18 – 0:57] Scene 2: Offline Verification Run — Good Fixture (Expected: VERIFIED)
* **Visual**: Click **▶ Run Good Fixture (Expected: VERIFIED)**. Pipeline steps through Baseline → Reproduce → Patch → Verify. Unified patch diff and generated reproduction test appear in tabs. Status banner turns emerald green: `[✔] STATUS: VERIFIED` / `EVIDENCE SATISFIED`.
* **Audio / Spoken Narration**:
  > "Here on our hosted web interface, we run RECON against the bundled shop project. The specification calls for a bulk discount at 10 or more units, but exactly 10 units are denied the discount. We click Run Good Fixture. In a temporary working copy, RECON runs the reproduction test on the original code, proving the bug fails twice. It applies the patch, confirms the repro test now passes, and verifies all existing tests still pass. Status: VERIFIED. This verdict is computed deterministically from real pytest exit codes."

### [0:57 – 1:26] Scene 3: Integrity & Regression Detection — Bad Fixture (Expected: UNVERIFIED)
* **Visual**: Click **▶ Run Bad Fixture (Expected: UNVERIFIED)**. Pipeline executes flawed patch. Status banner turns crimson: `[✖] STATUS: UNVERIFIED` / `REGRESSION DETECTED`. Verification reasons box lists the failing repro test and regressed existing test.
* **Audio / Spoken Narration**:
  > "Next, we click Run Bad Fixture. This patch modifies the discount rate instead of fixing the quantity threshold. RECON immediately catches that the reproduction test still fails and an existing unit test regressed. It halts with UNVERIFIED and flags REGRESSION DETECTED. Furthermore, RECON SHA-256 hashes all test files before and after patching, blocking unauthorized test modifications."

### [1:26 – 1:53] Scene 4: Local CLI Execution (Offline Fixture Mode)
* **Visual**: Command line terminal executing: `python -m recon --project examples/buggy_shop --bug-report examples/buggy_shop/bug_report.md --offline-fixtures examples/fixtures/good`. Shows `[offline mode] replaying canned model responses; no network, no credits used.` and `API calls: 2/2 (tokens reported: 0 in / 0 out)`. Git diff confirms original repository files are completely untouched.
* **Audio / Spoken Narration**:
  > "RECON can also be run locally via the command-line interface. In this screencast, we execute the CLI in offline fixture mode using bundled JSON fixtures. RECON executes the exact same verification pipeline without requiring network access or API credits, ensuring deterministic test evaluation and proving the original repository files remain completely untouched."

### [1:53 – 2:26] Scene 5: CLI Regression Handling & Live CLI vs. Browser Distinction
* **Visual**: Terminal executing bad fixture: `python -m recon ... --offline-fixtures examples/fixtures/bad`. Shows `UNVERIFIED (existing tests regressed: tests.test_pricing::test_large_order_gets_bulk_discount)`.
* **Audio / Spoken Narration**:
  > "When running the bad fixture in the CLI, RECON catches the regression on existing tests and halts with UNVERIFIED. To be crystal clear about how RECON runs: in production, the live CLI connects to NVIDIA Nemotron-3-Nano-30B-A3B on Nebius Token Factory using your own API key to generate reproduction tests and surgical patches. The hosted browser demo shown on Render runs strictly on bundled offline fixtures—making zero live API calls and requiring no secret keys or credits."

### [2:26 – 2:52] Scene 6: Security Model, Empirical Limits, and Wrap-Up
* **Visual**: GitHub repository README *Security Model & Limitations* section, displaying "No OS-Level Sandbox" and container/VM guidance.
* **Audio / Spoken Narration**:
  > "Finally, passing tests provide empirical evidence that the bug was resolved, not a mathematical proof. Because RECON runs pytest locally in a scrubbed environment rather than an OS-level sandbox, untrusted code should always be run inside a container or virtual machine. Clone RECON on GitHub and test verification-first bug fixing today. Thanks for watching!"

---

## 2. Synchronized Subtitles (SRT)

```srt
1
00:00:00,000 --> 00:00:17,800
Most AI coding agents say 'fixed it!' and move on. RECON does not take their word for it. It only reports VERIFIED when real pytest runs prove the bug was resolved without regressions.

2
00:00:18,000 --> 00:00:57,300
Bundled shop bug: discount spec requires 10 or more units, but exactly 10 units fail. We click Run Good Fixture. RECON verifies the bug on original code, applies the patch, confirms all tests pass, and reports STATUS: VERIFIED.

3
00:00:57,500 --> 00:01:26,080
Running the bad fixture: the patch changes the discount rate, not the threshold. RECON catches the test regression and halts with STATUS: UNVERIFIED / REGRESSION DETECTED. Test file hashing blocks test tampering.

4
00:01:26,280 --> 00:01:52,570
RECON CLI in offline fixture mode: runs the full verification pipeline locally with zero network calls and zero credit consumption, keeping original repository files completely untouched.

5
00:01:52,770 --> 00:02:25,920
CLI regression detection. Live CLI vs Offline Browser distinction: live CLI uses NVIDIA Nemotron-3-Nano-30B-A3B on Nebius Token Factory with your own key; hosted Render demo runs bundled offline fixtures with zero live calls.

6
00:02:26,120 --> 00:02:51,600
Passing tests are empirical evidence, not formal proof. RECON scrubs environment variables but is not an OS sandbox; run untrusted code in a container or VM. Clone RECON on GitHub to get started.
```
