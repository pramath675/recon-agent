"""Full pipeline with canned model responses: no network, no API key, no credits."""
import json
import shutil
from pathlib import Path

import pytest

from recon.agent import run_recon
from recon.config import Config
from recon.llm import FixtureLLM, LLMClient, LLMError
from recon.verify import COULD_NOT_REPRODUCE, ERROR, UNVERIFIED, VERIFIED

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "buggy_shop"
BUG = (DEMO / "bug_report.md").read_text()
GOOD_TEST = (ROOT / "examples/fixtures/good/repro_test.txt").read_text()
GOOD_PATCH = json.loads((ROOT / "examples/fixtures/good/patch.json").read_text())


class ScriptedLLM(LLMClient):
    """Returns scripted responses per stage; counts calls like the real client."""
    def __init__(self, script, max_calls=4):
        super().__init__(Config(max_api_calls=max_calls, model="scripted"))
        self.script = dict(script)

    def _send(self, stage, system, user):
        if stage not in self.script:
            raise LLMError(f"no script for {stage}")
        value = self.script[stage]
        return (value if isinstance(value, str) else json.dumps(value)), None


def go(tmp_path, llm, project=DEMO):
    return run_recon(project, BUG, Config(), llm, tmp_path / "out", say=lambda m: None)


def test_good_fixture_is_verified_and_original_untouched(tmp_path):
    before = (DEMO / "shop/pricing.py").read_text()
    report = go(tmp_path, FixtureLLM(ROOT / "examples/fixtures/good"))
    assert report["status"] == VERIFIED
    assert report["patch"]["changed_files"] == ["shop/pricing.py"]
    assert "+    if quantity >= BULK_THRESHOLD:" in report["patch"]["diff"]
    assert (DEMO / "shop/pricing.py").read_text() == before
    assert not (DEMO / "recon_generated").exists()
    assert (tmp_path / "out/recon_report.json").is_file() and (tmp_path / "out/patch.diff").is_file()
    assert report["api_usage"]["calls_made"] == 2


def test_wrong_patch_is_unverified(tmp_path):
    report = go(tmp_path, FixtureLLM(ROOT / "examples/fixtures/bad"))
    assert report["status"] == UNVERIFIED
    assert report["checks"]["repro_passes_after_patch"] is False


def test_test_that_passes_on_buggy_code_is_could_not_reproduce(tmp_path):
    passing = "from shop.pricing import line_total\n\ndef test_ok():\n    assert line_total(10.0, 1) == 10.0\n"
    llm = ScriptedLLM({"repro": {"test_code": passing}, "repro_repair": {"test_code": passing}})
    report = go(tmp_path, llm)
    assert report["status"] == COULD_NOT_REPRODUCE
    assert "patch" not in llm.usage.stages and llm.usage.calls == 2     # no patch call was spent


def test_patch_that_edits_the_repro_test_is_rejected(tmp_path):
    evil = {"edits": [{"path": "recon_generated/test_recon_repro.py",
                       "search": "== 90.0", "replace": "== 100.0"}]}
    llm = ScriptedLLM({"repro": {"test_code": GOOD_TEST}, "patch": evil, "patch_repair": evil})
    report = go(tmp_path, llm)
    assert report["status"] == UNVERIFIED
    assert "may not be modified" in " ".join(report["reasons"])


def test_dangerous_generated_test_is_never_executed(tmp_path):
    marker = tmp_path / "pwned"
    code = f"import os\n\ndef test_x():\n    os.system('touch {marker}')\n"
    llm = ScriptedLLM({"repro": {"test_code": code}, "repro_repair": {"test_code": code}})
    report = go(tmp_path, llm)
    assert report["status"] == COULD_NOT_REPRODUCE and not marker.exists()


def test_budget_stops_safely(tmp_path):
    llm = ScriptedLLM({"repro": {"test_code": GOOD_TEST}, "patch": GOOD_PATCH}, max_calls=1)
    report = go(tmp_path, llm)
    assert report["status"] == ERROR and "budget" in " ".join(report["reasons"]).lower()
    assert llm.usage.calls == 1


def test_repair_attempt_can_fix_a_bad_first_patch(tmp_path):
    bad = {"edits": [{"path": "shop/pricing.py", "search": "BULK_DISCOUNT = 0.10", "replace": "BULK_DISCOUNT = 0.20"}]}
    llm = ScriptedLLM({"repro": {"test_code": GOOD_TEST}, "patch": bad, "patch_repair": GOOD_PATCH})
    report = go(tmp_path, llm)
    assert report["status"] == VERIFIED and llm.usage.calls == 3
    assert [a["status"] for a in report["patch"]["attempts"]] == [UNVERIFIED, VERIFIED]


def test_missing_project_is_error_and_temp_dirs_cleaned(tmp_path):
    import glob, tempfile
    before = set(glob.glob(str(Path(tempfile.gettempdir()) / "recon_*")))
    report = go(tmp_path, ScriptedLLM({}), project=tmp_path / "nope")
    assert report["status"] == ERROR
    assert set(glob.glob(str(Path(tempfile.gettempdir()) / "recon_*"))) == before
