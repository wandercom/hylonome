"""Exercise the opt-in workbench flow with the real component package."""
import re
from urllib.parse import urlencode

import pytest

from kinbase_design.workbench import create_app
from tests.support import ROOT, request

KIT = ROOT / "integrations" / "wander-preview"
URL = "/wander-preview"
EDIT = {"sectionSpace": "xl", "cardGap": "lg", "tabletColumns": "one"}


def submit(app, **fields):
    return request(app, URL, "POST", urlencode(fields).encode(), "application/x-www-form-urlencoded")


def bundles(response):
    assert response["status"] == 200, response["body"].decode()
    return re.findall(r'href="(/wander-preview/render/[a-f0-9]{64})/index.html"', response["body"].decode())


def test_wander_preview_is_optional(library):
    app = create_app(library.library, library.workspace)
    assert b"Wander preview" not in request(app, "/")["body"]
    assert request(app, URL)["status"] == 404


@pytest.mark.browser
@pytest.mark.browser_timeout(90)
def test_wander_previews_save_layout_and_capture_both_pages(library):
    from playwright.sync_api import sync_playwright

    if not (KIT / "dist" / "preview.css").is_file():
        pytest.skip("Build the opt-in Wander integration with pnpm build to test published components.")
    app = create_app(library.library, library.workspace, wander_preview=KIT)
    initial = request(app, URL)
    before, = bundles(initial)
    assert before == bundles(request(app, URL))[0]
    initial_markup = request(app, before + "/index.html")["body"]
    assert b'data-slot="grid"' in initial_markup
    assert b'data-slot="property-card"' in initial_markup
    assert b"Stillwater House" in initial_markup
    assert b'class="capture-thumb"' in initial["body"]

    changed = submit(app, page="lake-stays", revision=0, **EDIT)
    assert changed["status"] == 303, changed["body"]
    assert submit(app, page="lake-stays", revision=0, **EDIT)["status"] == 400
    assert submit(app, page="lake-stays", revision=1, **{**EDIT, "cardGap": "99px"})["status"] == 400
    assert request(app, before + "/../../layout.json")["status"] == 404
    assert request(app, before + "/layout.json")["status"] == 404

    restarted = create_app(library.library, library.workspace, wander_preview=KIT)
    comparison = request(restarted, changed["headers"]["Location"])
    assert b"Before" in comparison["body"]
    initial_key, after = bundles(comparison)
    assert initial_key == before and after != before
    mountain_before, mountain_after = bundles(request(restarted, URL + "?page=mountain-stays"))
    assert mountain_before != before and mountain_after != after
    for bundle in (before, after, mountain_before, mountain_after):
        for width in (390, 768, 1280):
            shot = request(restarted, bundle + f"/{width}.png")
            assert shot["headers"]["Content-Type"] == "image/png"
            assert shot["body"].startswith(b"\x89PNG\r\n\x1a\n")
            assert int.from_bytes(shot["body"][16:20], "big") == width
    assert request(restarted, before + "/768.png")["body"] != request(restarted, after + "/768.png")["body"]

    with sync_playwright() as engine:
        browser = engine.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 768, "height": 900}, java_script_enabled=False)
            for bundle, gap, padding, two_columns in (
                (before, "24px", "32px", True),
                (after, "32px", "40px", False),
                (mountain_after, "32px", "40px", False),
            ):
                path = library.workspace / "wander-preview" / "renders" / bundle.rsplit("/", 1)[1] / "index.html"
                page.goto(path.as_uri(), wait_until="load")
                measurements = page.evaluate("""() => {
                  const grid = document.querySelector('[data-slot="grid"]');
                  const items = [...grid.children].map(item => item.getBoundingClientRect());
                  return {
                    gap: getComputedStyle(grid).columnGap,
                    pad: getComputedStyle(document.querySelector('main')).paddingBlockStart,
                    firstTwoShareRow: items[0].top === items[1].top,
                    overflow: document.documentElement.scrollWidth > innerWidth,
                    images: [...document.images].filter(image => image.naturalWidth > 0).length,
                  };
                }""")
                assert measurements == {
                    "gap": gap, "pad": padding, "firstTwoShareRow": two_columns,
                    "overflow": False, "images": 3,
                }
        finally:
            browser.close()
