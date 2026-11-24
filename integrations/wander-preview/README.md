# Wander component preview

The Hylonome workbench can render two property-results examples using Wander’s published React
components, design tokens, and Instrument Sans font. The pilot pins the package versions in the
`wander.com` lockfile when the pilot was built. The example text and generated property photos
are fictional.

## Run locally

Use Node 22.13 or newer, pnpm 10.13.1, and read access to Wander’s GitHub Packages. Configure GitHub
Packages authentication in your user npm configuration. The integration’s local registry config
only names the package scope.

From the Hylonome checkout, set up the workbench and Chromium if needed, then build the preview.

```sh
./scripts/setup-local.sh --with-browser
pnpm --dir integrations/wander-preview install --frozen-lockfile
pnpm --dir integrations/wander-preview build
.venv/bin/kinbase-design serve --wander-preview integrations/wander-preview
```

Open **Wander preview** at `http://127.0.0.1:8765/`. The workbench captures 390, 768, and 1280 px
screenshots on first view. The 390 px image represents a typical phone layout.
Change section padding, card gap, or the tablet column count and select
**Save layout and render** to compare the two layouts. Open the other example to see the saved
rules applied to different content.

For a design review, pick one change at a time and compare it at all three widths. If a
layout looks off, save the before and current screenshots and note the example, width,
and spacing or column choice that should change.

Layout edits and screenshots live in the configured private workspace under `wander-preview/`.
The layout applies to both examples. Each render is generated from the saved layout and captured
with local fonts and photos. Rebuild and restart the workbench after changing the preview package
or its renderer. The preview uses static markup for reviewing appearance.

## Test

```sh
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest tests/test_wander_preview.py
```

The browser test requires the optional preview build and real Chromium.
