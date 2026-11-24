import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import tailwind from "@tailwindcss/postcss";
import postcss from "postcss";

const root = dirname(fileURLToPath(import.meta.url));
const output = join(root, "dist");
const source = join(root, "preview.css");
const font = fileURLToPath(import.meta.resolve(
  "@wandercom/design-system-fonts/instrument-sans/instrument-sans.woff2",
));
const css = await postcss([tailwind({ base: root, optimize: true })])
  .process(await readFile(source, "utf8"), { from: source });

await mkdir(output, { recursive: true });
await copyFile(font, join(output, "instrument-sans.woff2"));
await writeFile(join(output, "preview.css"), css.css);
