"""Capture the static Wander preview in a bounded browser worker."""
import json
from pathlib import Path
import sys

from playwright.sync_api import Error

from ..artifacts.runtime import chromium, read_job, watch_parent
from ..checks.browser import prepare
from ..config import CAPTURE_TIMEOUT_MS, CHECK_VIEWPORT_HEIGHT


def capture(bundle, widths):
    with chromium() as browser:
        page = browser.new_page(
            device_scale_factor=1, java_script_enabled=False, reduced_motion="reduce",
        )
        page.route("http*://**/*", lambda route: route.abort())
        for width in widths:
            page.set_viewport_size({"width": width, "height": CHECK_VIEWPORT_HEIGHT})
            prepare(page, bundle / "index.html", timeout_ms=CAPTURE_TIMEOUT_MS)
            if not page.evaluate("""() => [...document.fonts].some(
                    font => font.family.replaceAll('"', '') === 'Instrument Sans' && font.status === 'loaded')
                    && [...document.images].every(image => image.naturalWidth > 0)"""):
                raise ValueError("Wander preview font or property photos could not load.")
            page.screenshot(
                path=bundle / f"{width}.png", full_page=True,
                animations="disabled", timeout=CAPTURE_TIMEOUT_MS,
            )


def main():
    watch_parent()
    try:
        job = read_job(Path(sys.argv[1]))
        capture(Path(job["bundle"]), job["widths"])
    except Error:
        print(json.dumps({"error": "Chromium could not capture the Wander preview. Check the local browser install."}))
        return 2
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
