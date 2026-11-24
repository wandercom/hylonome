"""Optional Wander component previews and private, reusable layout choices."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlencode

from ..storage import inside, read_json, write_json

PAGES = {"lake-stays": "Lakeside stays", "mountain-stays": "Mountain stays"}
WIDTHS = (390, 768, 1280)
OPTIONS = {
    "sectionSpace": ("Section padding", {"md": "24 px", "lg": "32 px", "xl": "40 px"}),
    "cardGap": ("Card gap", {"sm": "16 px", "md": "24 px", "lg": "32 px"}),
    "tabletColumns": ("Tablet columns", {"one": "One", "two": "Two"}),
}
DEFAULT_LAYOUT = {"sectionSpace": "lg", "cardGap": "md", "tabletColumns": "two"}
MEDIA = ("lake.webp", "forest.webp", "ridge.webp")
BUILD_FILES = ("preview.css", "instrument-sans.woff2")
SCREENSHOTS = tuple(f"{width}.png" for width in WIDTHS)
THUMB_TIMEOUT_MS = 8000
MAX_FORM_BYTES = 2048


def validated_layout(layout):
    if (not isinstance(layout, dict) or set(layout) != set(OPTIONS)
            or any(not isinstance(value, str) or value not in OPTIONS[name][1]
                   for name, value in layout.items())):
        raise ValueError("Choose a supported Wander layout value for each field.")
    return layout


def form_fields(environ):
    if environ.get("CONTENT_TYPE", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise ValueError("Expected a layout form.")
    length = int(environ.get("CONTENT_LENGTH", "0"))
    if not 0 < length <= MAX_FORM_BYTES:
        raise ValueError("Invalid layout form length.")
    body = environ["wsgi.input"].read(length)
    if len(body) != length:
        raise ValueError("Incomplete layout form.")
    fields = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=len(OPTIONS) + 2)
    if set(fields) != {*OPTIONS, "page", "revision"} or any(len(values) != 1 for values in fields.values()):
        raise ValueError("Invalid layout form fields.")
    return {key: values[0] for key, values in fields.items()}


class WanderPreview:
    def __init__(self, workspace, directory):
        self.root = inside(workspace, "wander-preview")
        self.state_path = inside(self.root, "layout.json")
        self.renders = inside(self.root, "renders")
        self.directory = Path(directory).expanduser().resolve()
        self.script = inside(self.directory, "render.mjs")
        package = read_json(inside(self.directory, "package.json"))
        self.versions = package["dependencies"]
        try:
            self.resources = {
                **{name: inside(self.directory, "dist", name).read_bytes() for name in BUILD_FILES},
                **{name: inside(self.directory, "photos", name).read_bytes() for name in MEDIA},
            }
        except FileNotFoundError as exc:
            raise ValueError("Build the optional Wander preview with pnpm install and pnpm build first.") from exc
        build_inputs = {
            **self.resources,
            "render.mjs": self.script.read_bytes(),
            "pnpm-lock.yaml": inside(self.directory, "pnpm-lock.yaml").read_bytes(),
            "workbench/wander.py": Path(__file__).read_bytes(),
        }
        self.fingerprint = {
            name: hashlib.sha256(content).hexdigest() for name, content in build_inputs.items()
        }

    def state(self):
        try:
            state = read_json(self.state_path)
        except FileNotFoundError:
            return {"revision": 0, "layout": DEFAULT_LAYOUT, "previous": None}
        validated_layout(state["layout"])
        if state["previous"] is not None:
            validated_layout(state["previous"])
        return state

    @contextmanager
    def locked(self, name):
        self.root.mkdir(parents=True, exist_ok=True)
        with inside(self.root, name).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def save(self, revision, layout, page):
        layout = validated_layout(layout)
        with self.locked("layout.lock"):
            state = self.state()
            if revision != state["revision"]:
                raise ValueError("The layout changed in another tab. Reload and try again.")
            if layout != state["layout"]:
                self.render(page, layout)
                write_json(self.state_path, {
                    "revision": state["revision"] + 1, "layout": layout, "previous": state["layout"],
                })

    def render(self, page, layout):
        inputs = {"page": page, "layout": validated_layout(layout)}
        key = hashlib.sha256(json.dumps({
            **inputs, "kit": self.fingerprint, "widths": WIDTHS,
        }, sort_keys=True).encode()).hexdigest()
        target = inside(self.renders, key)
        if target.is_dir():
            return key

        # Publish a bundle only after all screenshots are complete. Concurrent viewers
        # can reuse the same result and never see an incomplete directory.
        with self.locked("render.lock"):
            if target.is_dir():
                return key
            self.renders.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=self.renders, prefix=".render-") as staging:
                bundle = Path(staging) / key
                bundle.mkdir()
                try:
                    result = subprocess.run(
                        ["node", str(self.script)], input=json.dumps(inputs).encode(),
                        capture_output=True, cwd=self.directory, timeout=15, check=True,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    raise ValueError("Wander components could not render. Check Node and the optional package install.") from exc
                (bundle / "index.html").write_bytes(result.stdout)
                for name, content in self.resources.items():
                    (bundle / name).write_bytes(content)
                capture(bundle)
                bundle.rename(target)
        return key

    def handle(self, environ, segments, query, html):
        from . import RequestError

        method = environ.get("REQUEST_METHOD", "GET")
        if method == "GET" and len(segments) == 4 and segments[1] == "render":
            key, filename = segments[2:]
            if (not re.fullmatch(r"[0-9a-f]{64}", key)
                    or filename not in {"index.html", *BUILD_FILES, *MEDIA, *SCREENSHOTS}):
                raise RequestError("Unknown Wander preview resource", 404)
            content = inside(self.renders, key, filename).read_bytes()
            return 200, content, mimetypes.guess_type(filename)[0] or "application/octet-stream", []
        if segments != ["wander-preview"] or method not in {"GET", "POST"}:
            raise RequestError("Unknown Wander preview route", 404)

        fields = form_fields(environ) if method == "POST" else None
        page = fields.pop("page") if fields is not None else query.get("page", [next(iter(PAGES))])[0]
        if page not in PAGES:
            raise RequestError("Unknown Wander preview page", 404)
        if fields is not None:
            revision = int(fields.pop("revision"))
            self.save(revision, fields, page)
            return 303, b"", "text/html", [("Location", "/wander-preview?" + urlencode({"page": page}))]

        state = self.state()
        previews = []
        if state["previous"] is not None:
            previews.append(("Before", self.render(page, state["previous"])))
        previews.append(("Current layout", self.render(page, state["layout"])))
        return 200, html(
            "wander-preview.html", title="Wander preview", page=page, pages=PAGES, options=OPTIONS,
            state=state, widths=WIDTHS, previews=previews,
            web_version=self.versions["@wandercom/design-system-web"],
            token_version=self.versions["@wandercom/design-system-tokens"],
        ), "text/html; charset=utf-8", []


def capture(bundle):
    from playwright.sync_api import Error, sync_playwright

    from ..checks.browser import prepare

    try:
        with sync_playwright() as engine:
            browser = engine.chromium.launch(headless=True, timeout=THUMB_TIMEOUT_MS)
            try:
                page = browser.new_page(
                    device_scale_factor=1, java_script_enabled=False, reduced_motion="reduce",
                )
                page.route("http*://**/*", lambda route: route.abort())
                for width in WIDTHS:
                    page.set_viewport_size({"width": width, "height": 900})
                    prepare(page, bundle / "index.html", timeout_ms=THUMB_TIMEOUT_MS)
                    if not page.evaluate("""() => [...document.fonts].some(
                            font => font.family.replaceAll('"', '') === 'Instrument Sans' && font.status === 'loaded')
                            && [...document.images].every(image => image.naturalWidth > 0)"""):
                        raise ValueError("Wander preview font or property photos could not load.")
                    page.screenshot(
                        path=bundle / f"{width}.png", full_page=True,
                        animations="disabled", timeout=THUMB_TIMEOUT_MS,
                    )
            finally:
                browser.close()
    except Error as exc:
        raise ValueError("Chromium could not capture the Wander preview. Check the local browser install.") from exc
