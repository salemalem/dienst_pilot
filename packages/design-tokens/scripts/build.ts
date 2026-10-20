/** Build: tokens.json → dist/tokens.css, dist/tailwind.css, dist/fonts/, src/generated/native.ts. */
import { copyFileSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { basename } from "node:path";
import { fileURLToPath } from "node:url";

import { toCss, toNative, toTailwind } from "./emit.ts";
import { loadSource, resolve, SOURCE_DIR } from "./source.ts";

const root = fileURLToPath(new URL("../", import.meta.url));
const dist = `${root}dist/`;
const generated = `${root}src/generated/`;

const tokens = resolve(loadSource());

rmSync(dist, { recursive: true, force: true });
mkdirSync(`${dist}fonts`, { recursive: true });
mkdirSync(generated, { recursive: true });

writeFileSync(`${dist}tokens.css`, toCss(tokens));
writeFileSync(`${dist}tailwind.css`, toTailwind(tokens));
writeFileSync(`${generated}native.ts`, toNative(tokens));
for (const font of tokens.fonts) {
  copyFileSync(`${SOURCE_DIR}${font.file}`, `${dist}fonts/${basename(font.file)}`);
}
copyFileSync(`${SOURCE_DIR}fonts/OFL.txt`, `${dist}fonts/OFL.txt`);

console.log(`design-tokens: built ${tokens.name} v${tokens.version} (web + native)`);
