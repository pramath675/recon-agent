# Before you claim RECON works

Tick each box only after YOU have seen it pass on your own machine.

- [ ] `pip install -r requirements.txt` succeeds in a fresh virtual environment.
- [ ] `python -m pytest` -> all unit tests pass (no API key needed).
- [ ] Offline demo (good fixtures) prints **VERIFIED** and exits with code 0.
- [ ] Offline demo (bad fixtures) prints **UNVERIFIED** and exits with code 1.
- [ ] `examples/buggy_shop/shop/pricing.py` is byte-for-byte unchanged after the demos (`git diff` is empty).
- [ ] `python -m recon --check-config` reports all three Nebius variables as `set` (values are never printed).
- [ ] You looked up the Nebius base URL and the exact NVIDIA model ID in the Nebius console/docs and pasted them into `.env`.
- [ ] API run completes (any status). Inspect `recon_output/recon_report.json`: `api_usage.calls_made` <= your budget.
- [ ] You READ the generated `recon_output/test_recon_repro.py` and agree it tests the reported bug.
- [ ] You checked your Nebius console for actual usage after the run.
- [ ] `.env` is not tracked: `git status` does not list it, and `git log -p` contains no key.
- [ ] README claims match what you actually observed (do not claim model results you did not see).
- [ ] If the real API run fails (HTTP error, model returns non-JSON), you can explain why from the report's `api_usage.errors`.
