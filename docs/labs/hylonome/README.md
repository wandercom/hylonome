# Hylonome on Wander Labs

`hylonome.md` is the article source for `/blogs/hylonome`. The Labs edition uses
the existing Markdown post loader and blog route; no separate app or template is
needed there. Copy the Markdown into `wandercom/labs/content/posts/hylonome.md`
when updating that edition.

The standalone preview uses the same article source and the versioned
`wander-labs-editorial` language previously derived from Wander Labs' vendored
Wander Design System. It demonstrates reuse: the page imports the generated
generic CSS without importing the reference material. The Labs edition already
consumes the upstream Wander Design System and does not load a competing theme.

From this directory, render the portable article with Pandoc:

```sh
pandoc hylonome.md --from=gfm --to=html5 --standalone --toc --toc-depth=2 \
  --template=preview.template.html --output=index.html
```

For an offline single-file preview, inline both local stylesheet links and replace the
font URL with its WOFF2 data URL.
The font license is in `assets/FONT-LICENSE.txt`. No raw imports or original
captures are bundled here. This directory does not deploy the article.
