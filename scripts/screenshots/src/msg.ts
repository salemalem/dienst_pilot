import { messages } from "@dienstpilot/i18n";
import { IntlMessageFormat } from "intl-messageformat";

import { LANG } from "./env.ts";

type Tree = { [k: string]: string | Tree };

/** A catalog message in the language of this run, formatted like the apps do (ICU). */
export function msg(key: string, values: Record<string, string | number> = {}): string {
  let node: string | Tree | undefined = messages[LANG] as unknown as Tree;
  for (const part of key.split(".")) node = typeof node === "object" ? node[part] : undefined;
  if (typeof node !== "string") throw new Error(`no message ${key}`);
  return String(new IntlMessageFormat(node, LANG).format(values));
}
