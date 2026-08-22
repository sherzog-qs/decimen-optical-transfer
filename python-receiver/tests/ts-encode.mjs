// The cross-language encounter: the TypeScript ENCODER produces frames, the
// Python receiver will rebuild them. Emits a frame dump + meta the Python side
// reads. Nothing reimplemented — the point is that the two languages meet.
import { writeFileSync } from "node:fs";
import { LTEncoder } from "../../shared/fountain.ts";
import { packFrame, fnv1a } from "../../shared/protocol.ts";
import { packFile } from "../../shared/protocol.ts";

const [outFrames, outMeta] = process.argv.slice(2);

// 300 KB incompressible so the container stays uncompressed and byte-checkable.
// Real randomness — an LCG's low bits compress. crypto caps at 65536/call.
const original = new Uint8Array(300 * 1024);
for (let o = 0; o < original.length; o += 65536) {
  crypto.getRandomValues(original.subarray(o, Math.min(o + 65536, original.length)));
}
const packed = await packFile("report.bin", "application/octet-stream", original);
if (packed.compression !== "none") throw new Error("expected incompressible");

const frameBytes = 2953;
const blockLen = frameBytes - 22;
const sessionId = 4242;
const enc = new LTEncoder(packed.container, blockLen, sessionId);
const header = {
  sessionId, seq: 0, k: enc.k, blockLen,
  totalLen: packed.container.length, payloadFnv: fnv1a(packed.container), flags: 0,
};

const frames = [];
let dropped = 0;
for (let seq = 0; seq < enc.k * 3; seq++) {
  if ((seq * 7919) % 100 < 15) { dropped++; continue; }   // 15% loss
  frames.push(packFrame({ ...header, seq }, enc.encode(seq)));
}
const total = frames.reduce((n, f) => n + f.length, 0);
const dump = new Uint8Array(total);
let off = 0;
for (const f of frames) { dump.set(f, off); off += f.length; }
writeFileSync(outFrames, dump);
writeFileSync(outMeta, JSON.stringify({
  frameLen: frameBytes, k: enc.k, sent: frames.length, dropped,
  sha256: Buffer.from(await crypto.subtle.digest("SHA-256", original)).toString("hex"),
  size: original.length,
}));
console.log(JSON.stringify({ k: enc.k, sent: frames.length, dropped }));
