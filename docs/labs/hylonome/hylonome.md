---
title: "Hylonome: a design language you can put in Git"
summary: "A local workbench for taking an existing design, making its rules explicit, and carrying those rules into the next page."
date: 2026-11-23
author:
  name: Wander Labs
  role: Engineering
tags: [engineering, design]
---

Suppose you’re adding a page to an existing site. You can copy the last page and change the words. That gets you a page, but it leaves you guessing which parts of the original were decisions and which just happened to be there. If the next person copies your page, they inherit both.

We wanted a way to carry forward the decisions without copying the page. [Hylonome](https://github.com/wandercom/hylonome) is a local workbench for doing that. It takes in an existing design, gives you a draft language you can inspect and change, and exports an approved version that another project can use.

## What the import knows

Start with design tokens, a Figma export, or a page Hylonome can visit without signing in. Tokens tell you the values a system exposes; a page tells you which values show up together. Neither tells you why a particular heading is small. It could be a section title or a display title squeezed into a narrow column. They can look alike on one screen and need different rules on the next.

Hylonome measures what it can, proposes mappings from the evidence, and shows alternatives where it can’t settle the mapping. Review the same sample content at different widths. If your title is supposed to wrap on a phone, look at a long title on a phone. The draft keeps track of where values came from, so you can distinguish a token the source supplied from a role you chose.

## What goes in Git

The shared library is a directory you choose. Put it in the repo that owns the language if you want teams to review and reuse it there. It contains the working language, approved assets, and immutable versions. Raw captures and original uploads stay in a separate private workspace. A font or image becomes part of the shared package only when you promote it.

That makes a correction concrete. If a type size is wrong, change it in the language, validate it, and export the new version. Another repo can pin the result and decide when to take the update. Hylonome can emit plain CSS or DTCG tokens with Tailwind v4 CSS. Its Apply workflow compares the language against an inventory of what the target site needs and prepares a handoff. The receiving repo still owns its implementation and deployment.

## We used it on this page

For this post we started from the Wander Design System tokens already used by Labs. We kept its monochrome palette, type scale, and reading width in a versioned language called `wander-labs-editorial`. The portable preview uses that language’s CSS export. The Labs edition goes through the existing blog template, so it inherits the same type and layout as the rest of the site.

The point of keeping the language is what happens on the next page. An engineer can see which decisions they’re inheriting, make a deliberate exception if the page needs one, and leave the decisions intact for whoever comes next.

[Hylonome source and workflow documentation](https://github.com/wandercom/hylonome#readme)
