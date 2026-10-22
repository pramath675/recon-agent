import json

import pytest

from recon.patching import PatchError, apply_edits, make_diff, parse_patch


def project(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())
    return tmp_path


def edit(path="pkg/mod.py", search="x = 1", replace="x = 2"):
    return parse_patch({"edits": [{"path": path, "search": search, "replace": replace}]})


def test_applies_and_diffs(tmp_path):
    root = project(tmp_path, {"pkg/mod.py": "x = 1\n"})
    changes = apply_edits(root, edit())
    assert (root / "pkg/mod.py").read_text() == "x = 2\n"
    assert "-x = 1" in make_diff(changes) and "+x = 2" in make_diff(changes)


def test_preserves_crlf(tmp_path):
    root = project(tmp_path, {"pkg/mod.py": "x = 1\r\ny = 3\r\n"})
    apply_edits(root, edit())
    assert (root / "pkg/mod.py").read_bytes() == b"x = 2\r\ny = 3\r\n"


@pytest.mark.parametrize("bad", ["../evil.py", "/etc/passwd.py", "C:/x.py", "pkg/../../x.py", "pkg\\..\\x.py"])
def test_rejects_unsafe_paths(tmp_path, bad):
    root = project(tmp_path, {"pkg/mod.py": "x = 1\n"})
    with pytest.raises(PatchError):
        apply_edits(root, edit(path=bad))


@pytest.mark.parametrize("protected", ["tests/test_a.py", "pkg/test_mod.py", "pkg/mod_test.py", "conftest.py",
                                       "recon_generated/test_recon_repro.py", "tests/helpers.py", "pytest.ini"])
def test_rejects_protected_files(tmp_path, protected):
    root = project(tmp_path, {protected: "x = 1\n"})
    with pytest.raises(PatchError):
        apply_edits(root, edit(path=protected))


def test_rejects_non_python_and_missing_files(tmp_path):
    root = project(tmp_path, {"README.md": "x = 1\n"})
    with pytest.raises(PatchError):
        apply_edits(root, edit(path="README.md"))
    with pytest.raises(PatchError):
        apply_edits(root, edit(path="pkg/new.py"))


def test_rejects_symlink(tmp_path):
    root = project(tmp_path, {"real.py": "x = 1\n"})
    try:
        (root / "link.py").symlink_to(root / "real.py")
    except OSError:
        pytest.skip("OS does not permit symlink creation")
    with pytest.raises(PatchError):
        apply_edits(root, edit(path="link.py"))


def test_search_must_match_exactly_once(tmp_path):
    root = project(tmp_path, {"pkg/mod.py": "x = 1\nx = 1\n"})
    with pytest.raises(PatchError, match="2 times"):
        apply_edits(root, edit())
    with pytest.raises(PatchError, match="not found"):
        apply_edits(root, edit(search="nope = 0"))


def test_rejects_syntax_errors_and_writes_nothing(tmp_path):
    root = project(tmp_path, {"pkg/mod.py": "x = 1\n"})
    with pytest.raises(PatchError, match="not valid Python"):
        apply_edits(root, edit(replace="x = ("))
    assert (root / "pkg/mod.py").read_text() == "x = 1\n"


def test_rejects_dangerous_added_code(tmp_path):
    root = project(tmp_path, {"pkg/mod.py": "x = 1\n"})
    with pytest.raises(PatchError, match="forbidden"):
        apply_edits(root, edit(replace="import subprocess"))


@pytest.mark.parametrize("obj", [None, [], {}, {"edits": []}, {"edits": "x"}, {"edits": [1]},
                                 {"edits": [{"path": "a.py", "search": "", "replace": "x"}]},
                                 {"edits": [{"path": "a.py", "search": "a", "replace": "a"}]},
                                 {"edits": [{"path": "a.py", "search": "a"}]},
                                 {"edits": [{"path": "a.py", "search": "a", "replace": "b"}] * 6}])
def test_rejects_malformed_patches(obj):
    with pytest.raises(PatchError):
        parse_patch(obj)
