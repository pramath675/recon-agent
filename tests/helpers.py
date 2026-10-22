from recon.runner import ERROR, FAILED, NO_TESTS, PASSED, TIMEOUT, RunResult


def run(outcome, tests=None, label="x"):
    return RunResult(label=label, outcome=outcome, exit_code=0, duration_s=0.0, tests=tests or {})


FAIL_RUN = run(FAILED, {"t::repro": "failed"})
PASS_RUN = run(PASSED, {"t::repro": "passed"})
