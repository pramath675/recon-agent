from recon.runner import ERROR, FAILED, NO_TESTS, PASSED, TIMEOUT
from recon.verify import COULD_NOT_REPRODUCE, UNVERIFIED, VERIFIED, check_baseline, evaluate

from .helpers import FAIL_RUN, PASS_RUN, run

SUITE_OK = run(PASSED, {"a::t1": "passed", "a::t2": "passed"})


def verdict(**over):
    args = dict(baseline_repro_runs=[FAIL_RUN, FAIL_RUN], patch_error=None, tamper_problems=[],
                post_repro_runs=[PASS_RUN, PASS_RUN], baseline_existing=SUITE_OK, post_existing=SUITE_OK)
    args.update(over)
    return evaluate(**args)


def test_verified_happy_path():
    v = verdict()
    assert v.status == VERIFIED
    assert all(v.checks[k] for k in ("baseline_failure_established", "patch_valid", "tests_untampered",
                                     "repro_passes_after_patch", "existing_tests_ok"))


def test_baseline_pass_is_could_not_reproduce():
    assert verdict(baseline_repro_runs=[PASS_RUN]).status == COULD_NOT_REPRODUCE


def test_baseline_timeout_or_error_is_not_a_reproduction():
    for outcome in (TIMEOUT, ERROR, NO_TESTS):
        v = verdict(baseline_repro_runs=[run(outcome)])
        assert v.status == COULD_NOT_REPRODUCE
        assert outcome in " ".join(v.reasons)


def test_inconsistent_baseline_is_could_not_reproduce():
    assert verdict(baseline_repro_runs=[FAIL_RUN, PASS_RUN]).status == COULD_NOT_REPRODUCE


def test_empty_baseline_never_verified():
    assert verdict(baseline_repro_runs=[]).status == COULD_NOT_REPRODUCE


def test_patch_error_is_unverified():
    v = verdict(patch_error="path traversal", post_repro_runs=[], post_existing=None)
    assert v.status == UNVERIFIED and "path traversal" in " ".join(v.reasons)


def test_tampering_blocks_verified_even_if_everything_passes():
    v = verdict(tamper_problems=["protected file modified: recon_generated/test_recon_repro.py"])
    assert v.status == UNVERIFIED and v.checks["tests_untampered"] is False


def test_repro_still_failing_or_timeout_after_patch():
    for bad in (FAIL_RUN, run(TIMEOUT), run(ERROR)):
        assert verdict(post_repro_runs=[bad]).status == UNVERIFIED


def test_no_post_runs_is_unverified():
    assert verdict(post_repro_runs=[]).status == UNVERIFIED


def test_flaky_rerun_is_unverified():
    assert verdict(post_repro_runs=[PASS_RUN, FAIL_RUN]).status == UNVERIFIED


def test_existing_test_regression_is_unverified():
    after = run(FAILED, {"a::t1": "passed", "a::t2": "failed"})
    v = verdict(post_existing=after)
    assert v.status == UNVERIFIED and "a::t2" in " ".join(v.reasons)


def test_deleted_passing_test_counts_as_regression():
    after = run(PASSED, {"a::t1": "passed"})
    assert verdict(post_existing=after).status == UNVERIFIED


def test_existing_suite_timeout_or_error_is_unverified():
    for bad in (run(TIMEOUT), run(ERROR), None):
        assert verdict(post_existing=bad).status == UNVERIFIED


def test_preexisting_failures_that_stay_failing_do_not_block():
    before = run(FAILED, {"a::t1": "passed", "a::old": "failed"})
    after = run(FAILED, {"a::t1": "passed", "a::old": "failed"})
    v = verdict(baseline_existing=before, post_existing=after)
    assert v.status == VERIFIED


def test_new_failure_alongside_preexisting_blocks():
    before = run(FAILED, {"a::t1": "passed", "a::old": "failed"})
    after = run(FAILED, {"a::t1": "failed", "a::old": "failed"})
    assert verdict(baseline_existing=before, post_existing=after).status == UNVERIFIED


def test_no_existing_tests_allowed_by_default_but_can_be_required():
    none = run(NO_TESTS)
    assert verdict(baseline_existing=none, post_existing=none).status == VERIFIED
    assert verdict(baseline_existing=none, post_existing=none, require_existing_tests=True).status == UNVERIFIED


def test_check_baseline_requires_all_runs_failed():
    ok, _ = check_baseline([FAIL_RUN, FAIL_RUN])
    assert ok
