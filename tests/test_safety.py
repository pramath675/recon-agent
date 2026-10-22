import pytest

from recon.fs import copy_project, is_secret_name
from recon.safety import diff_snapshots, is_protected_path, scan_patch_text, scan_test_code, snapshot_protected

GOOD = "from pkg.mod import f\n\ndef test_f():\n    assert f(1) == 2\n"


def test_good_test_passes_scan():
    assert scan_test_code(GOOD) == []


@pytest.mark.parametrize("code", [
    "import os\ndef test_a():\n    os.system('x')\n",
    "import subprocess\ndef test_a(): pass\n",
    "from urllib.request import urlopen\ndef test_a(): pass\n",
    "def test_a():\n    eval('1')\n",
    "def test_a():\n    open('/etc/passwd')\n",
    "def test_a(:\n",
    "def helper(): pass\n",
    "",
])
def test_bad_tests_are_rejected(code):
    assert scan_test_code(code)


def test_protected_paths():
    assert is_protected_path("tests/x.py") and is_protected_path("a/test_b.py") and is_protected_path("conftest.py")
    assert not is_protected_path("shop/pricing.py")


def test_snapshot_detects_tampering(tmp_path):
    (tmp_path / "tests").mkdir()
    t = tmp_path / "tests" / "test_a.py"
    t.write_text("def test_a(): pass\n")
    before = snapshot_protected(tmp_path)
    assert diff_snapshots(before, snapshot_protected(tmp_path)) == []
    t.write_text("def test_a(): assert True\n")
    assert any("modified" in p for p in diff_snapshots(before, snapshot_protected(tmp_path)))
    t.unlink()
    assert any("removed" in p for p in diff_snapshots(before, snapshot_protected(tmp_path)))


def test_patch_text_scan():
    assert scan_patch_text("return a + b") == []
    assert scan_patch_text("import socket") and scan_patch_text("eval(x)") and scan_patch_text("os.system('x')")


def test_copy_skips_secrets_venvs_git_and_symlinks(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    for rel in ["a.py", ".env", "keys/server.pem", ".venv/lib.py", ".git/config", "__pycache__/a.pyc", "sub/ok.py"]:
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("x")
    try:
        (src / "link.py").symlink_to(src / "a.py")
    except OSError:
        pytest.skip("OS does not permit symlink creation")
    (src / "big.bin").write_bytes(b"0" * 6_000_000)
    stats = copy_project(src, dst)
    copied = sorted(p.relative_to(dst).as_posix() for p in dst.rglob("*") if p.is_file())
    assert copied == ["a.py", "sub/ok.py"]
    assert stats["skipped_large_files"] == ["big.bin"]
    assert is_secret_name(".env.local") and is_secret_name("my_secret.txt")
