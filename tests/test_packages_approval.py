"""Design packages by path, saving to a target, and sign-off by configured approvers.

Oracles: the shipped Harbor language and a draft from the authored DTCG fixture; the
approver list comes from a test-owned config file and identity from a test-owned stand-in
`gh` executable on PATH. These tests were written alongside the implementation.

Falsifiers: an external package that cannot be applied without copying it into the
library; a saved package that loses its vocabulary when moved; an approval by an account
the installation does not trust; a typed login accepted without the GitHub CLI; Apply
proceeding past a required sign-off.
"""
import json
import os
import shutil
import sys

import pytest

from tests.factory_task_support import recorder
from tests.m4_support import git, inventory_document, site_repository
from tests.support import FIXTURES, ROOT


def portable_harbor(library, tmp_path):
    """Harbor as a package outside the library, carrying its vocabulary."""
    package = tmp_path / "elsewhere" / "packages" / "harbor"
    shutil.copytree(ROOT / "library" / "languages" / "harbor", package)
    version = json.loads((package / "working.json").read_text())["vocabulary"]
    shutil.copytree(ROOT / "library" / "vocabulary" / version, package / "vocabulary" / version)
    assert not library.path("harbor").exists()
    return package


@pytest.fixture
def approvers(library, tmp_path):
    """A stand-in GitHub CLI that reports one authenticated login, and an approver list."""
    bin_dir = tmp_path / "gh-bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f"#!{sys.executable}\nimport os,sys\n"
                  "if sys.argv[1:3]==['api','user']:\n print(os.environ.get('STAND_IN_GH_LOGIN',''))\n sys.exit(0 if os.environ.get('STAND_IN_GH_LOGIN') else 1)\n"
                  "sys.exit(1)\n")
    gh.chmod(0o755)
    config = tmp_path / "local-config" / "config.toml"
    config.parent.mkdir()
    def configure(*logins, require=False, login="design-approver"):
        config.write_text("[approval]\napprovers = " + json.dumps(list(logins)) + f"\nrequire = {'true' if require else 'false'}\n")
        library.command_env.update({"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "HYLONOME_CONFIG": str(config),
                                    "STAND_IN_GH_LOGIN": login})
    return configure


def test_an_external_package_works_by_path_and_records_return_home(library, tmp_path):
    package = portable_harbor(library, tmp_path)
    path = str(package)
    assert library.json("validate", path)["accepted"]
    resolved = library.json("resolve", path, "listing-card.price")["properties"]["color"]["value"]
    assert resolved == json.loads((package / "working.json").read_text())["style"]["color"]["primary"]["$value"]
    before = set((package / "versions").iterdir())
    reference = library.json("mint", path)["ref"]
    version = reference.split("@")[1]
    assert (package / "versions" / (version + ".json")).is_file()
    assert set((package / "versions").iterdir()) >= before
    exported = library.json("export", path, "--adapter", "generic", "--out", tmp_path / "export")
    assert exported["language"] == reference and (tmp_path / "export" / "roles.css").is_file()
    assert not library.path("harbor").exists(), "a path package must not be copied into the library"


def test_two_external_package_edits_keep_the_revision_chain(library, tmp_path):
    package = portable_harbor(library, tmp_path)
    path = str(package)
    initial = library.json("language-history", path)
    version = initial["current"]
    archived = {p.name: p.read_bytes() for p in (package / "versions").glob("*.json")}
    receipts = []
    for reason, color in (("First tone", "#345678"), ("Second tone", "#234567")):
        receipt = library.json("revise-language", path, "--changes", json.dumps({
            "/style/color/primary/$value": color}), "--reason", reason, "--expected-version", version)
        assert receipt["changed"]
        receipts.append((version, receipt["version"], reason))
        version = receipt["version"]
    # Each CLI invocation opens a fresh staging directory, including this read.
    reopened = library.json("language-history", path)
    assert reopened["current"] == version
    assert reopened["revisions"][:len(initial["revisions"])] == initial["revisions"]
    assert [(r["before"], r["after"], r["reason"])
            for r in reopened["revisions"][len(initial["revisions"]):]] == receipts
    assert all((package / "versions" / name).read_bytes() == data for name, data in archived.items())


def test_a_package_without_its_vocabulary_is_refused_clearly(library, tmp_path):
    package = portable_harbor(library, tmp_path)
    document = json.loads((package / "working.json").read_text())
    document["vocabulary"] = "v999"
    (package / "working.json").write_text(json.dumps(document))
    result = library.json("validate", str(package), code=2)
    assert "v999" in result["error"]
    assert "error" in library.json("validate", str(tmp_path / "not-a-package"), code=2)


def test_save_draft_writes_a_portable_package_to_a_target(library, tmp_path):
    artifact = library.json("import-artifact", "--file", FIXTURES / "ingest-tokens.json", "--kind", "dtcg")["artifact"]
    library.json("draft", "--from", artifact, "--language", "from-tokens", cwd=library.project, timeout=120)
    target = tmp_path / "another-project" / "packages"
    saved = library.json("save-draft", "from-tokens", "--target", target, cwd=library.project, timeout=120)
    package = target / "from-tokens"
    assert saved["saved"] and saved["package"] == str(package)
    assert not library.path("from-tokens").exists()
    version = json.loads((package / "working.json").read_text())["vocabulary"]
    assert (package / "vocabulary" / version / "vocabulary.json").is_file()
    assert (package / "provenance" / (saved["hash"] + ".json")).is_file()
    # Moved to yet another place and opened by a library that has never seen it.
    moved = tmp_path / "moved" / "from-tokens"
    shutil.move(str(package), moved)
    assert library.json("validate", str(moved))["accepted"]
    default = library.json("save-draft", "from-tokens", cwd=library.project, timeout=120)
    assert default["saved"] and library.path("from-tokens").is_file()


def test_sign_off_needs_a_configured_approver_verified_by_the_github_cli(library, tmp_path, approvers):
    package = portable_harbor(library, tmp_path)
    path = str(package)
    approvers()
    assert "No approvers" in library.json("approve", path, code=2)["error"]
    approvers("lead-designer", login="someone-else")
    assert "not a configured approver" in library.json("approve", path, code=2)["error"]
    approvers("lead-designer", login="")
    assert "Cannot verify a GitHub identity" in library.json("approve", path, code=2)["error"]
    assert library.json("approvals", path)["approved"] is False
    approvers("Lead-Designer", login="lead-designer")
    approved = library.json("approve", path, "--note", "Matches the brand review")
    version = approved["language"].split("@")[1]
    assert approved["approved"] and approved["approvers"] == ["lead-designer"]
    records = json.loads((package / "approvals" / (version + ".json")).read_text())
    assert [(r["approver"], r["method"], r["version"], r["note"]) for r in records] == [
        ("lead-designer", "github-cli", version, "Matches the brand review")]
    # Approving again adds nothing; a second configured approver is appended.
    library.json("approve", path)
    approvers("lead-designer", "second-reviewer", login="second-reviewer")
    assert library.json("approve", path)["approvers"] == ["lead-designer", "second-reviewer"]
    # An installation that no longer trusts an account no longer counts its record.
    approvers("someone-new", login="someone-new")
    status = library.json("approvals", path)
    assert status["approved"] is False and [r["configured"] for r in status["records"]] == [False, False]
    # A changed design is a new version, and needs its own sign-off.
    approvers("lead-designer", login="lead-designer")
    document = json.loads((package / "working.json").read_text())
    document["style"]["color"]["primary"]["$value"] = "#0a5f57"
    (package / "working.json").write_text(json.dumps(document))
    assert library.json("approvals", path)["approved"] is False


def test_apply_from_a_path_honours_required_sign_off_and_factory_can_reopen_it(library, tmp_path, approvers):
    package = portable_harbor(library, tmp_path)
    repo = site_repository(tmp_path)
    (repo / "kinbase-design.inventory.json").write_text(json.dumps(inventory_document()))
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "Inventory")
    library.command_env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "KINBASE_DESIGN_FACTORY": ""})
    approvers("lead-designer", require=True, login="lead-designer")
    args = ["apply", str(package), "--site", repo, "--adapter", "generic", "--target-dir", "design", "--branch"]
    refused = library.json(*args, cwd=library.project, timeout=90, code=2)
    assert "requires sign-off" in refused["error"] and git(repo, "branch", "--list").strip() == "* main"
    library.json("approve", str(package))
    result = library.json(*args, cwd=library.project, timeout=90)
    record = json.loads((library.workspace / "handoffs" / result["handoff"] / "handoff.json").read_text())
    assert record["package"] == str(package) and record["approval"]["approved"]
    assert "Sign-off: approved by lead-designer" in (library.workspace / "handoffs" / result["handoff"] / "TASK.md").read_text()
    spy = recorder(tmp_path / "entrypoint")
    submitted = library.json("factory-task", result["handoff"], "--run", "path-package", "--dry-run", timeout=60)
    assert submitted["invoked"] is False and not spy.receipt.exists()
