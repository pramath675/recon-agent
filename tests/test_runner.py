import sys

import pytest

from recon.runner import ERROR, FAILED, NO_TESTS, PASSED, TIMEOUT, classify, run_pytest


def make(tmp_path, body):
    (tmp_path / "test_x.py").write_text(body)
    return tmp_path


def test_classify_is_pure_and_distinguishes_causes():
    assert classify(0, False, {}) == PASSED
    assert classify(1, False, {"a": "failed"}) == FAILED
    assert classify(1, False, {"a": "error"}) == ERROR       # setup/fixture error is not a test failure
    assert classify(2, False, {}) == ERROR                   # collection error
    assert classify(5, False, {}) == NO_TESTS
    assert classify(None, True, {}) == TIMEOUT


def test_real_pass_and_fail(tmp_path):
    assert run_pytest(make(tmp_path, "def test_a():\n    assert True\n")).outcome == PASSED
    r = run_pytest(make(tmp_path, "def test_a():\n    assert 1 == 2\n"))
    assert r.outcome == FAILED and r.failed_ids and "assert" in r.output_tail


def test_collection_error_is_error_not_failure(tmp_path):
    assert run_pytest(make(tmp_path, "import does_not_exist_xyz\ndef test_a(): pass\n")).outcome == ERROR


def test_no_tests(tmp_path):
    assert run_pytest(make(tmp_path, "x = 1\n")).outcome == NO_TESTS


def test_timeout_is_killed_and_reported(tmp_path):
    r = run_pytest(make(tmp_path, "import time\ndef test_a():\n    time.sleep(30)\n"), timeout=2)
    assert r.outcome == TIMEOUT and r.duration_s < 15


def test_api_key_not_visible_to_tested_code(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "super-secret-value")
    body = "import os\ndef test_a():\n    assert 'NEBIUS_API_KEY' not in os.environ\n"
    assert run_pytest(make(tmp_path, body)).outcome == PASSED
