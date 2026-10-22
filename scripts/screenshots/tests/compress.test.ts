import sharp from "sharp";
import { expect, test } from "vitest";

import { recompress } from "../src/compress.ts";

test("recompress keeps every pixel and never grows the file", async () => {
  const raw = Buffer.alloc(64 * 48 * 4);
  for (let i = 0; i < raw.length; i++) raw[i] = (i * 7 + (i >> 5)) % 251;
  const png = await sharp(raw, { raw: { width: 64, height: 48, channels: 4 } })
    .png({ compressionLevel: 0 })
    .toBuffer();
  const out = await recompress(png);
  expect(out.length).toBeLessThanOrEqual(png.length);
  const a = await sharp(png).raw().toBuffer();
  const b = await sharp(out).raw().toBuffer();
  expect(b.equals(a)).toBe(true);
});
