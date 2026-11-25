"""The design contract committed with an Apply branch is integrity-checked like the export.

A Factory run reads the builder's contract and gives the Tester the expected values.
Falsifiers: submit a hand-off whose contract copy (above all the tester's oracle) was
altered, removed or extended; omit the contract from the directive; fail to mark the
oracle as tester-only.
"""
import hashlib
import json

import pytest

from tests.factory_task_support import TARGET, assert_refusal, directive_document, prepare_handoff, recorder, task_cli
from tests.m4_support import git

ORACLE = "kinbase-design/expected.json"


@pytest.fixture
def factory_case(library, language, tmp_path):
    case = prepare_handoff(library, language, tmp_path)
    spy = recorder(tmp_path / "entrypoint")
    library.command_env["KINBASE_DESIGN_FACTORY"] = str(spy.path)
    return case, spy


def test_directive_lists_every_contract_file_and_marks_the_oracle(factory_case):
    case, _ = factory_case
    task_cli(case, "contract", dry=True)
    _, payload, prose = directive_document(case.bundle / "directive.md")
    record = json.loads((case.bundle / "handoff.json").read_text())
    assert ORACLE in record["contract_files"] and "kinbase-design/CONTRACT.md" in record["contract_files"]
    listed = {entry["path"]: entry for entry in payload["contract_files"]}
    assert not set(listed) & {entry["path"] for entry in payload["files"]}  # the export list is unchanged
    for name in record["contract_files"]:
        entry = listed[TARGET + "/" + name]
        committed = git(case.repo, "show", f"{case.commit}:{TARGET}/{name}", binary=True)
        assert entry["sha256"] == hashlib.sha256(committed).hexdigest()
        assert entry["role"] == ("tester-only" if name == ORACLE else "contract")
    assert payload["oracle"] == TARGET + "/" + ORACLE and payload["contract"] == TARGET + "/kinbase-design/CONTRACT.md"
    assert "Tester only" in prose and "Withhold it from the Coder" in prose


@pytest.mark.parametrize("failure", ["altered-oracle", "missing-oracle", "extra-contract-file", "manifest-drops-oracle"])
def test_a_changed_contract_is_refused_before_factory_runs(factory_case, failure):
    case, spy = factory_case
    oracle = case.bundle / "contract" / "expected.json"
    if failure == "altered-oracle":
        oracle.write_text(oracle.read_text().replace("#", "#0", 1))
    elif failure == "missing-oracle":
        oracle.unlink()
    elif failure == "extra-contract-file":
        (case.bundle / "contract" / "markup" / "invented.html").write_text("<div></div>")
    else:
        path = case.bundle / "handoff.json"
        record = json.loads(path.read_text())
        record["contract_files"] = [name for name in record["contract_files"] if name != ORACLE]
        path.write_text(json.dumps(record))
    assert git(case.repo, "rev-parse", case.branch) == case.commit
    assert_refusal(case, spy, task_cli(case, "refused", factory=spy.path, code=1))


def test_a_hand_off_from_before_the_contract_still_submits(factory_case):
    case, _ = factory_case
    path = case.bundle / "handoff.json"
    record = json.loads(path.read_text())
    del record["contract_files"]
    path.write_text(json.dumps(record))
    for file in sorted((case.bundle / "contract").rglob("*"), reverse=True):
        file.unlink() if file.is_file() else file.rmdir()
    (case.bundle / "contract").rmdir()
    task_cli(case, "legacy", dry=True)
    _, payload, _ = directive_document(case.bundle / "directive.md")
    assert payload["oracle"] is None and payload["contract_files"] == []


def test_the_directive_carries_the_request_and_the_compliance_check(factory_case):
    case, _ = factory_case
    path = case.bundle / "handoff.json"
    record = json.loads(path.read_text())
    record["request"] = "Build a checkout page for this site."
    record["verify_pages"] = ["http://localhost:3000/checkout"]
    path.write_text(json.dumps(record))
    task_cli(case, "with-request", dry=True)
    text, payload, prose = directive_document(case.bundle / "directive.md")
    assert payload["request"] == "Build a checkout page for this site."
    assert "> Build a checkout page for this site." in prose
    assert payload["acceptance_command"].startswith("kinbase-design verify " + record["language"])
    assert "--page http://localhost:3000/checkout" in payload["acceptance_command"]
    assert "exit 0 is required" in prose
