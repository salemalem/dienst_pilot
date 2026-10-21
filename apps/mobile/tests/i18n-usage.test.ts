// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import de from "../../../packages/i18n/de.json" with { type: "json" };
import en from "../../../packages/i18n/en.json" with { type: "json" };

const ROOTS = [join(import.meta.dirname, "../src"), join(import.meta.dirname, "../app")];

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(f) ? [p] : [];
  });
}

type Tree = { [k: string]: string | Tree };
function has(tree: Tree, path: string): boolean {
  let node: string | Tree | undefined = tree;
  for (const part of path.split(".")) {
    if (typeof node !== "object") return false;
    node = node[part];
  }
  return node !== undefined;
}

describe("staff app strings go through the catalog", () => {
  const all = ROOTS.flatMap(files);

  it("every literal t(...) key exists in German and English", () => {
    const missing: string[] = [];
    for (const f of all) {
      const src = readFileSync(f, "utf8");
      if (!/useTranslation\(/.test(src)) continue;
      for (const m of src.matchAll(/\bt\(\s*"([\w.]+)"/g)) {
        const key = String(m[1]);
        for (const [name, cat] of [
          ["de", de],
          ["en", en],
        ] as const) {
          if (!has(cat as Tree, key)) missing.push(`${name}: ${key} (${f})`);
        }
      }
    }
    expect(missing).toEqual([]);
  });

  it("no screen carries hard-coded words in JSX text", () => {
    const offenders: string[] = [];
    for (const f of all.filter((x) => x.endsWith(".tsx"))) {
      const src = readFileSync(f, "utf8");
      for (const m of src.matchAll(/>([^<>{}=;&|()\n]*[A-Za-zÄÖÜäöüß]{3,}[^<>{}=;&|()\n]*)</g)) {
        const text = m[1]?.trim() ?? "";
        const line = src.slice(src.lastIndexOf("\n", m.index), m.index + m[0].length);
        if (/Promise<|=>|<[A-Z]\w*[,>]/.test(line) && !/<\/?[a-z]/.test(line)) continue;
        if (text && !/^(DienstPilot|C[1-8])$/.test(text)) offenders.push(`${f}: ${text}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("every control has an accessible name: no <Pressable> without a label", () => {
    const bare: string[] = [];
    for (const f of all.filter((x) => x.endsWith(".tsx"))) {
      const src = readFileSync(f, "utf8");
      for (const m of src.matchAll(/<Pressable\b([\s\S]*?)>/g)) {
        if (!/accessibilityLabel=/.test(m[1] ?? "")) bare.push(f);
      }
    }
    expect(bare).toEqual([]);
  });
});
