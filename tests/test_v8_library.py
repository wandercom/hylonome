"""Vocabulary v8: the full element library and the standard preview pages.

Oracles: the published v8 vocabulary and samples, read through the CLI, and the bytes the
renderer writes. Expected compositions (which constructs each page holds) come from the
samples file the vocabulary ships, so a page that silently drops a construct fails.
These tests were written alongside the implementation.

Falsifiers: a library construct that appears on no standard page; a checkout that still
needs the contact-form slots; a field control without its label; a states page missing a
declared state; new constructs leaking into the five classic pages; a migrated language
that loses validity.
"""
import json
import re
import shutil

import pytest

from tests.support import PAGES as CLASSIC, ROOT, V8_EXTRA_PAGES as NEW_PAGES


@pytest.fixture
def v8(library):
    return library.json("vocabulary", "--vocabulary", "v8")


@pytest.fixture
def samples():
    return json.loads((ROOT / "library" / "vocabulary" / "v8" / "samples.json").read_text())


@pytest.fixture
def shipped(library):
    for name in ("harbor", "lantern"):
        shutil.copytree(ROOT / "library" / "languages" / name, library.path(name).parent)
    return library


def test_v8_is_the_default_and_keeps_every_v7_contract(library, v8):
    v7 = library.json("vocabulary", "--vocabulary", "v7")
    assert library.json("vocabulary")["version"] == "v8"
    assert set(v7["constructs"]) < set(v8["constructs"])
    for name, contract in v7["constructs"].items():
        if name == "form":
            continue
        assert v8["constructs"][name] == contract, name
    form = {slot["id"]: slot for slot in v8["constructs"]["form"]["slots"]}
    assert {s for s, d in form.items() if d["required"]} == {"title", "action"}
    assert form["fields"]["content-only"] and form["fields"]["element"] == "div"
    assert set(v8["context"]["pages"]) == set(CLASSIC) | set(NEW_PAGES)
    for name in ("field", "fieldset", "choice-group", "stepper", "order-summary", "line-item", "table", "pagination",
                 "breadcrumb", "tabs", "dialog", "alert", "description-list", "stat", "pricing-tier", "page-header"):
        assert name in v8["constructs"], name
    for name, contract in v8["constructs"].items():
        ids = [slot["id"] for slot in contract["slots"]]
        assert contract["contract"]["reading-order"] == [i for i in contract["contract"]["reading-order"] if i in ids], name
        assert set(contract["contract"]["focus-order"]) <= set(ids), name
        for slot in contract["slots"]:
            assert slot["role"] in v8["roles"] and slot["emphasis"] in v8["emphasis"], (name, slot["id"])


def test_every_construct_appears_on_a_standard_page_or_the_states_page(v8, samples):
    def constructs(items):
        for item in items:
            yield item["construct"]
            yield from constructs(item.get("children", []))
            for children in item.get("slot_children", {}).values():
                yield from constructs(children)
    composed = {name for page in samples["compositions"].values() for name in constructs(page["instances"])}
    classic = {name for page in CLASSIC[:-1] for name in samples["pages"][page]}
    assert set(samples["pages"]["states.html"]) == set(v8["constructs"])
    chrome = {"site-header", "nav", "footer", "empty-state", "error-state"}  # every page, or the states page's stress section
    assert set(v8["constructs"]) <= composed | classic | chrome
    assert set(samples["examples"]) == composed - classic - {"form", "collection", "card", "content-section"}


def test_shipped_languages_migrate_to_v8_and_build_every_page(shipped, tmp_path, v8, samples):
    for name in ("harbor", "lantern"):
        document = shipped.read(name)
        v7 = shipped.json("vocabulary", "--vocabulary", "v7")
        assert document["vocabulary"] == "v8" and set(v8["constructs"]) - set(v7["constructs"]) <= set(document["components"])
        assert shipped.json("validate", name)["accepted"]
        out = tmp_path / name
        shipped.json("build-preview", name, "--out", out)
        assert {p.name for p in out.glob("*.html")} == set(CLASSIC) | set(NEW_PAGES)
        for page in NEW_PAGES:
            html = (out / page).read_text()
            for link in v8["context"]["pages"]:
                assert f'href="{link}"' in html, (name, page, link)
        for page in CLASSIC[:-1]:
            html = (out / page).read_text()
            assert 'data-kd-construct="field"' not in html and 'data-kd-construct="table"' not in html


def test_checkout_is_a_general_form_with_labelled_fields(shipped, tmp_path):
    out = tmp_path / "harbor"
    shipped.json("build-preview", "harbor", "--out", out)
    html = (out / "checkout.html").read_text()
    form = re.search(r'<form data-kd-construct="form"[^>]*>(.*?)</form>', html, re.S)[1]
    assert 'data-kd-slot="form.name"' not in form and 'data-kd-slot="form.fields"' in form
    controls = re.findall(r'<(input|select|textarea)\b([^>]*)>', form)
    labelled = 0
    for tag, attrs in controls:
        identifier = re.search(r'\bid="([^"]+)"', attrs)
        if identifier:
            assert f'for="{identifier[1]}"' in form, identifier[1]
            labelled += 1
    assert labelled >= 10
    assert re.search(r'<input[^>]*type="radio"', form) and re.search(r'<select', form)
    postcode = re.search(r'<input[^>]*id="postcode"[^>]*>', form)[0]
    assert 'aria-invalid="true"' in postcode and 'aria-describedby="postcode-error"' in postcode
    assert 'id="postcode-error"' in form
    summary = re.search(r'<aside data-kd-construct="order-summary"[^>]*>', html)[0]
    assert 'aria-label="Order summary"' in summary
    assert html.count('data-kd-construct="line-item"') == 6 and html.count('data-kd-construct="step"') == 4


def test_the_states_page_shows_every_construct_in_every_declared_state(shipped, tmp_path, v8):
    out = tmp_path / "lantern"
    shipped.json("build-preview", "lantern", "--out", out)
    html = (out / "states.html").read_text()
    for name, contract in v8["constructs"].items():
        for state in contract["states"]:
            assert re.search(rf'data-kd-construct="{re.escape(name)}"[^>]*data-kd-state="{state}"', html), (name, state)
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), "specimen identifiers must be unique on the page"


def test_the_contract_pack_carries_v8_markup(shipped, tmp_path):
    from tests.m4_support import git, inventory_document, site_repository
    repo = site_repository(tmp_path)
    (repo / "kinbase-design.inventory.json").write_text(json.dumps(inventory_document()))
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "Inventory")
    result = shipped.json("apply", "harbor", "--site", repo, "--adapter", "generic", "--target-dir", "design",
                          "--request", "Build a checkout page", cwd=shipped.project, timeout=120)
    markup = shipped.workspace / "handoffs" / result["handoff"] / "contract" / "markup"
    assert '<input' in (markup / "field.html").read_text()
    assert '<td data-kd-construct="table-cell"' in (markup / "table-cell.html").read_text()
    expected = json.loads((markup.parent / "expected.json").read_text())
    assert {"field", "order-summary", "table-cell"} <= set(expected["contracts"])


@pytest.mark.browser
@pytest.mark.browser_timeout(1500)
@pytest.mark.parametrize("name", ["harbor", "lantern"])
def test_shipped_languages_pass_rendered_checks_on_every_v8_page(shipped, tmp_path, name):
    result = shipped.json("check", name, "--out", tmp_path / name, "--widths", "320,1280", code=(0, 1), timeout=1400)
    blocking = [(f["rule"], f.get("target")) for f in result["findings"] if f["type"] in {"violation", "missing"} and not f.get("exception")]
    assert result["accepted"], blocking
    assert set(result["checked"]["pages"]) == set(CLASSIC) | set(NEW_PAGES)
