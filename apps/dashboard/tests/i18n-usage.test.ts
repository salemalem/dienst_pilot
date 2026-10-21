import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import de from "../../../packages/i18n/de.json" with { type: "json" };
import en from "../../../packages/i18n/en.json" with { type: "json" };
import { describe, expect, it } from "vitest";

const SRC = join(import.meta.dirname, "../src");

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

/**
 * Every `t("key")` call, with the namespaces its function name was bound to in the file
 * (`const t = useTranslations("ns")`; a file may bind the same name in several components).
 */
function usages(source: string): { key: string; candidates: string[] }[] {
  const bound = new Map<string, string[]>();
  for (const m of source.matchAll(/const (\w+) = useTranslations\((?:"([\w.]+)")?\)/g)) {
    bound.set(String(m[1]), [...(bound.get(String(m[1])) ?? []), m[2] ?? ""]);
  }
  const out: { key: string; candidates: string[] }[] = [];
  for (const [fn, spaces] of bound) {
    for (const c of source.matchAll(new RegExp(`\\b${fn}\\(\\s*"([\\w.]+)"`, "g"))) {
      out.push({
        key: String(c[1]),
        candidates: spaces.map((ns) => (ns ? `${ns}.${String(c[1])}` : String(c[1]))),
      });
    }
  }
  return out;
}

describe("dashboard strings go through the catalog", () => {
  const all = files(SRC);

  it("every literal t(...) key exists in German and English", () => {
    const missing: string[] = [];
    for (const f of all) {
      for (const { key, candidates } of usages(readFileSync(f, "utf8"))) {
        for (const [name, cat] of [
          ["de", de],
          ["en", en],
        ] as const) {
          if (!candidates.some((c) => has(cat as Tree, c)))
            missing.push(`${name}: ${key} (${f.replace(SRC, "")})`);
        }
      }
    }
    expect(missing).toEqual([]);
  });

  it("no component carries hard-coded words in JSX text", () => {
    const offenders: string[] = [];
    for (const f of all.filter((x) => x.endsWith(".tsx"))) {
      const src = readFileSync(f, "utf8");
      // Text between a closing > and the next < or {, containing a run of letters.
      for (const m of src.matchAll(/>([^<>{}=;&|()\n]*[A-Za-zÄÖÜäöüß]{3,}[^<>{}=;&|()\n]*)</g)) {
        const text = m[1]?.trim() ?? "";
        const line = src.slice(src.lastIndexOf("\n", m.index), m.index + m[0].length);
        if (/Promise<|=>|<[A-Z]\w*[,>]/.test(line) && !/<\/?[a-z]/.test(line)) continue;
        if (text && !/^(DienstPilot|C[1-8]|W\d+)$/.test(text))
          offenders.push(`${f.replace(SRC, "")}: ${text}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
