// The encounter point: does the TypeScript receiver read what Python sends?
//
// Reads a frame dump produced by ts_roundtrip.py, decodes it with the very
// modules the web receiver uses, and reports what came out. Nothing here is
// re-implemented — that is the whole point.
import { readFileSync, writeFileSync } from "node:fs";
import { LTDecoder } from "../../shared/fountain.ts";
import { parseFrame, unpackFile } from "../../shared/protocol.ts";

const [dumpPath, metaPath, outPath] = process.argv.slice(2);
const dump = new Uint8Array(readFileSync(dumpPath));
const meta = JSON.parse(readFileSync(metaPath, "utf8"));

const frameLen = meta.frameLen;
let decoder = null;
let parsed = 0;
let rejected = 0;

for (let off = 0; off + frameLen <= dump.length; off += frameLen) {
  const frame = dump.subarray(off, off + frameLen);
  const result = parseFrame(frame);
  if (!result) { rejected++; continue; }
  parsed++;
  const { header, block } = result;
  // Everything the decoder needs comes off the frame — no handshake, no
  // shared state with the encoder.
  decoder ??= new LTDecoder(header.k, header.blockLen, header.sessionId, header.totalLen);
  decoder.addFrame(header.seq, block);
  if (decoder.isComplete) break;
}

const report = { parsed, rejected, complete: Boolean(decoder?.isComplete) };
if (decoder?.isComplete) {
  const container = decoder.assemble();
  const file = await unpackFile(container);   // verifies SHA-256 or throws
  report.name = file.name;
  report.type = file.type;
  report.bytes = file.bytes.length;
  report.compression = file.compression;
  writeFileSync(outPath, file.bytes);
}
console.log(JSON.stringify(report));
