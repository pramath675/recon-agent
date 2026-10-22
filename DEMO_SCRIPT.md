# RECON demo video script (~2 minutes)

**0:00 – Hook (screen: README title).**
"AI coding agents say 'fixed it!' and move on. RECON doesn't take their word for it. It only reports VERIFIED when real test results prove the bug existed and is gone."

**0:15 – The bug (screen: `examples/buggy_shop/bug_report.md` and `shop/pricing.py`).**
"Here's a small shop library. The docs say 10 or more units get a discount, but exactly 10 units don't. All existing tests pass, so the bug is invisible to them."

**0:30 – Offline run, no credits (terminal).**
`python -m recon --project examples/buggy_shop --bug-report examples/buggy_shop/bug_report.md --offline-fixtures examples/fixtures/good`
Narrate the steps: existing tests pass → generated test FAILS on the original code (bug reproduced, twice) → patch applied only in a temp copy → test passes, existing tests still pass → **VERIFIED**.
"The status is computed by Python from pytest results, not by the model."

**1:00 – Integrity (terminal).**
Run with `--offline-fixtures examples/fixtures/bad`. Show **UNVERIFIED**: "A wrong patch is caught because the reproduction test still fails and an existing test regressed."
"Patches can't touch tests; if they try, it's rejected."

**1:20 – Real model run (terminal).**
`python -m recon --project examples/buggy_shop --bug-report examples/buggy_shop/bug_report.md`
"Same pipeline, with an NVIDIA open model on Nebius Token Factory. Two model calls, hard budget, no retries, no loops."
Show the API usage line and `recon_output/recon_report.json`.

**1:45 – Honesty (screen: README 'Limitations').**
"Passing tests are evidence, not proof. The generated test is LLM-written, so a human should read it. And this is not a security sandbox: use a container for untrusted code."

**1:55 – Close.** "RECON: verification-first bug fixing. Thanks!"
