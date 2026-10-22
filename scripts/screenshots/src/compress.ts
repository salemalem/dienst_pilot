import sharp from "sharp";

/**
 * Re-encode a PNG without changing a single pixel: maximum zlib effort, adaptive filtering, no palette
 * reduction. Returns the smaller of the two files.
 */
export async function recompress(png: Buffer): Promise<Buffer> {
  const out = await sharp(png)
    .png({ compressionLevel: 9, effort: 10, adaptiveFiltering: true, palette: false })
    .toBuffer();
  return out.length < png.length ? out : png;
}
