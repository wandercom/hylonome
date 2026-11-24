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

from ..artifacts.runtime import run_job
from ..config import CAPTURE_TIMEOUT_MS
from ..storage import inside, read_json, write_json

PAGES = {"lake-stays": "Lakeside stays", "mountain-stays": "Mountain stays"}
# The Wander pilot reviews a typical phone width. The main workbench's checks
# also use 320 px to catch reflow on narrower screens.
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
MAX_FORM_BYTES = 2048
DEFAULT_LAYOUT_NOTICE = "The saved layout could not be loaded. Save to replace it with your current choices."


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
            "workbench/wander_worker.py": Path(__file__).with_name("wander_worker.py").read_bytes(),
        }
        self.fingerprint = {
            name: hashlib.sha256(content).hexdigest() for name, content in build_inputs.items()
        }

    def state(self):
        defaults = {"revision": 0, "layout": DEFAULT_LAYOUT, "previous": None, "notice": None}
        try:
            state = read_json(self.state_path)
        except FileNotFoundError:
            return defaults
        except ValueError:
            return {**defaults, "notice": DEFAULT_LAYOUT_NOTICE}
        revision = state.get("revision") if isinstance(state, dict) else None
        if type(revision) is not int or revision < 0:
            return {**defaults, "notice": DEFAULT_LAYOUT_NOTICE}
        try:
            layout = validated_layout(state.get("layout"))
        except ValueError:
            return {**defaults, "revision": revision, "notice": DEFAULT_LAYOUT_NOTICE}
        previous = state.get("previous")
        notice = None
        if previous is not None:
            try:
                validated_layout(previous)
            except ValueError:
                previous = None
                notice = "The previous layout could not be loaded. Your current layout is still available."
        return {"revision": revision, "layout": layout, "previous": previous, "notice": notice}

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
            if layout != state["layout"] or state["notice"]:
                self.render(page, layout)
                write_json(self.state_path, {
                    "revision": state["revision"] + 1, "layout": layout,
                    "previous": state["layout"] if layout != state["layout"] else state["previous"],
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
                run_job("kinbase_design.workbench.wander_worker",
                        {"bundle": str(bundle), "widths": WIDTHS},
                        timeout=2 * CAPTURE_TIMEOUT_MS / 1000)
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
