import { readFileSync } from "node:fs";
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PropertyCard } from "@wandercom/design-system-web/blocks/property-card";
import { Button } from "@wandercom/design-system-web/ui/button";
import { Container } from "@wandercom/design-system-web/ui/container";
import { Grid, GridItem } from "@wandercom/design-system-web/ui/grid";

const homes = {
  lake: {
    name: "Stillwater House",
    location: "Lake Crescent, Washington",
    alt: "Modern timber house beside a lake at dusk",
    features: { bedrooms: 3, baths: 2 },
    price: 745,
  },
  forest: {
    name: "Fern Hollow",
    location: "Hood River, Oregon",
    alt: "Cedar cabin among evergreen trees",
    features: { bedrooms: 2, baths: 2 },
    price: 595,
  },
  ridge: {
    name: "Highline Lodge",
    location: "White Salmon, Washington",
    alt: "Dark timber lodge with a mountain view",
    features: { bedrooms: 4, baths: 3 },
    price: 885,
  },
};

const pages = {
  "lake-stays": { title: "Lakeside stays", homes: ["lake", "forest", "ridge"] },
  "mountain-stays": { title: "Mountain stays", homes: ["ridge", "forest", "lake"] },
};

function ResultsPage({ page, layout }) {
  const results = pages[page];
  const span = { base: "full", md: layout.tabletColumns === "two" ? 3 : 6, lg: 4 };
  return h("html", { lang: "en" },
    h("head", null,
      h("meta", { charSet: "utf-8" }),
      h("meta", { name: "viewport", content: "width=device-width, initial-scale=1" }),
      h("title", null, results.title),
      h("link", { rel: "stylesheet", href: "preview.css" }),
    ),
    h("body", { className: "bg-surface-primary text-primary font-sans" },
      h("main", { style: { paddingBlock: `var(--spacing-layout-${layout.sectionSpace})` } },
        h(Container, { asChild: true, className: "mb-layout-lg" },
          h("header", { className: "flex flex-wrap items-end justify-between gap-layout-sm" },
            h("div", null,
              h("h1", { className: "text-display md:text-display-lg font-medium" }, results.title),
              h("p", { className: "mt-layout-2xs text-body-lg text-secondary" }, "Pacific Northwest"),
            ),
            h(Button, { asChild: true, variant: "outline" }, h("a", { href: "#results" }, "View homes")),
          ),
        ),
        h(Grid, {
          id: "results",
          "aria-label": "Homes",
          style: { gap: `var(--spacing-layout-${layout.cardGap})` },
        }, results.homes.map((key) =>
          h(GridItem, { key, id: key, span, className: "min-w-0" },
            h(PropertyCard, {
              name: homes[key].name,
              location: homes[key].location,
              features: homes[key].features,
              price: homes[key].price,
              images: [{ src: `${key}.webp`, alt: homes[key].alt }],
              href: `#${key}`,
              showRating: false,
              showWishlist: false,
              isSwipeable: false,
            }),
          ),
        )),
      ),
    ),
  );
}

const input = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write("<!doctype html>" + renderToStaticMarkup(h(ResultsPage, input)));
