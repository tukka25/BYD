import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";

/* The pictures on the landing page's cards (public/previews/, made by
   scripts/previews.mjs) must show the dashboards as they are now. A dashboard
   file that changed since its picture was taken fails here. A change to how
   dashboards are drawn does not, so take the pictures again after one too. */

const AGAIN = "run npm run build && npm run previews";
const MAX_BYTES = 150 * 1024;
const SITE = new URL("../", import.meta.url);
const DIR = new URL("data/dashboards/", SITE);
const names = readdirSync(DIR)
  .filter((file) => file.endsWith(".json"))
  .map((file) => file.replace(/\.json$/, ""))
  .sort();

type Entry = { file: string; width: number; height: number; sha256: string };
const record = JSON.parse(readFileSync(new URL("data/previews.json", SITE), "utf8")) as {
  dashboards: Record<string, Entry>;
};

/** Width and height from a WebP file's RIFF header: the VP8X chunk's canvas
    when there is one (Chrome writes VP8X, ICCP, then VP8), else the first
    VP8 (lossy) or VP8L (lossless) frame. */
function webpSize(bytes: Uint8Array): { width: number; height: number } {
  const ascii = (at: number) => String.fromCharCode(...bytes.subarray(at, at + 4));
  if (bytes.length < 20 || ascii(0) !== "RIFF" || ascii(8) !== "WEBP") throw new Error("not a WebP file");
  const u16 = (at: number) => bytes[at] | (bytes[at + 1] << 8);
  const u24 = (at: number) => bytes[at] | (bytes[at + 1] << 8) | (bytes[at + 2] << 16);
  const u32 = (at: number) => (u24(at) | (bytes[at + 3] << 24)) >>> 0;
  for (let at = 12; at + 8 <= bytes.length; ) {
    const kind = ascii(at);
    const size = u32(at + 4);
    const data = at + 8;
    if (kind === "VP8X") return { width: 1 + u24(data + 4), height: 1 + u24(data + 7) };
    if (kind === "VP8 ") {
      if (bytes[data + 3] !== 0x9d || bytes[data + 4] !== 0x01 || bytes[data + 5] !== 0x2a) {
        throw new Error("VP8 chunk without its start code");
      }
      return { width: u16(data + 6) & 0x3fff, height: u16(data + 8) & 0x3fff };
    }
    if (kind === "VP8L") {
      if (bytes[data] !== 0x2f) throw new Error("VP8L chunk without its signature");
      const bits = u32(data + 1);
      return { width: 1 + (bits & 0x3fff), height: 1 + ((bits >>> 14) & 0x3fff) };
    }
    at = data + size + (size % 2); // a chunk is padded to an even size
  }
  throw new Error("no VP8X, VP8 or VP8L chunk");
}

/* A RIFF file holding the given chunks, for the reader's own test. */
function riff(...chunks: [string, number[]][]): Uint8Array {
  const body: number[] = [..."WEBP"].map((c) => c.charCodeAt(0));
  for (const [kind, data] of chunks) {
    body.push(...[...kind].map((c) => c.charCodeAt(0)), ...le(data.length, 4), ...data);
    if (data.length % 2) body.push(0);
  }
  return Uint8Array.from([..."RIFF"].map((c) => c.charCodeAt(0)).concat(le(body.length, 4), body));
}
const le = (value: number, bytes: number) => Array.from({ length: bytes }, (_, i) => (value >>> (8 * i)) & 0xff);

test("the WebP reader takes the size from VP8X, VP8 and VP8L headers", () => {
  // VP8X: flags and 3 reserved bytes, then canvas width - 1 and height - 1 in 24 bits each.
  const extended = riff(["VP8X", [0x20, 0, 0, 0, ...le(639, 3), ...le(799, 3)]], ["ICCP", [1, 2, 3]]);
  assert.deepEqual(webpSize(extended), { width: 640, height: 800 });
  // VP8: a 3-byte frame tag, the start code 9d 01 2a, then 14-bit width and height.
  const lossy = riff(["VP8 ", [0, 0, 0, 0x9d, 0x01, 0x2a, ...le(321, 2), ...le(0x4000 | 123, 2)]]);
  assert.deepEqual(webpSize(lossy), { width: 321, height: 123 });
  // VP8L: the signature 2f, then width - 1 and height - 1 in 14 bits each.
  const lossless = riff(["VP8L", [0x2f, ...le(99 | (49 << 14), 4)]]);
  assert.deepEqual(webpSize(lossless), { width: 100, height: 50 });
  // An unknown chunk of odd size first: its padding byte is skipped.
  assert.deepEqual(webpSize(riff(["XYZW", [1]], ["VP8L", [0x2f, ...le(0, 4)]])), { width: 1, height: 1 });
  assert.throws(() => webpSize(Uint8Array.from(readFileSync(new URL("app/icon.svg", SITE)))), /not a WebP file/);
});

for (const name of names) {
  test(`${name} has a picture of its current dashboard file`, () => {
    const entry = record.dashboards[name];
    assert.ok(entry, `data/previews.json has no picture of ${name}: ${AGAIN}`);
    const sha256 = createHash("sha256").update(readFileSync(new URL(`${name}.json`, DIR))).digest("hex");
    assert.equal(entry.sha256, sha256, `data/dashboards/${name}.json changed after its picture was taken: ${AGAIN}`);
    assert.equal(entry.file, `/previews/${name}.webp`);

    const image = new URL(`public${entry.file}`, SITE);
    assert.ok(existsSync(image), `public${entry.file} is missing: ${AGAIN}`);
    const bytes = statSync(image).size;
    assert.ok(bytes < MAX_BYTES, `public${entry.file} is ${bytes} bytes, at or over ${MAX_BYTES}`);
    assert.deepEqual(webpSize(readFileSync(image)), { width: entry.width, height: entry.height });
  });
}

test("every picture names a dashboard that exists", () => {
  assert.deepEqual(
    Object.keys(record.dashboards).filter((name) => !names.includes(name)),
    [],
    `data/previews.json names a dashboard with no file in data/dashboards/: ${AGAIN}`,
  );
});
