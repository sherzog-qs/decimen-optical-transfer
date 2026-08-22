# Architecture

Three pages, one shared core, a handful of single-purpose build plugins. No framework, no state library — each page is one TypeScript module wiring DOM to the shared code.

## Pages

| dir | page | entry |
|---|---|---|
| `/` | home: cards, share dialog | `home/main.ts` |
| `send/` | file/snippet → fountain-coded QR stream on a canvas | `send/main.ts` |
| `receive/` | camera → WASM QR decode in workers → fountain decoder → file | `receive/main.ts`, `receive/worker.ts` |

The send page carries two non-entry modules: `send/qr-frame.ts`, the one QR
generation path (pinned mask, version locking) shared by the live stream and
the exporter so the two cannot drift apart, and `send/export.ts`, the
animation exporter — the stream rendered into a looping APNG or a
PNG-sequence ZIP, DOM-free so the whole pipeline is Node-tested
(`tests/animation-export.test.ts` pins its frames pixel-for-pixel to the
rasterizer, and its size forecast samples a real frame rather than modeling
one).

## Shared modules (`shared/`)

- `fountain.ts` — LT encoder/decoder, deterministic soliton distribution (see [Protocol](protocol.md)).
- `protocol.ts` — frame header pack/parse, file container, SHA-256 verification, stream identity.
- `frame-capacity.ts` — QR capacity math: payload size → block length / count limits.
- `qr-raster.ts` — QR module matrix → RGBA raster.
- `png.ts` — bilevel (1 bit per pixel, 2-entry palette) PNG primitives: chunk writer, CRC-32, scanline packing with an integer upscale baked in, deflate via the same `CompressionStream` the container uses. Palette rather than grayscale is deliberate — ffmpeg's APNG decoder refuses 1-bit grayscale, which would strand the export for the video pipelines it targets.
- `apng.ts` — APNG assembly over `png.ts`: `acTL`/`fcTL`/`fdAT`, exact rational frame delays, infinite loop.
- `zip.ts` — store-mode ZIP writer for the PNG-sequence export; structure only, the PNGs are already deflated.
- `display.ts` — QR display-size fitting against the viewport.
- `platform.ts` — `isIOS`/`isAndroid` sniffs and camera capability probing (torch, continuous focus, max fps). Policy: probe wherever probeable; sniff only for unprobeable behavior.
- `worker-pool.ts` — decode worker pool; busy workers drop frames, the fountain absorbs it.
- `no-signal.ts` — pure timing policy for the "Nothing happening?" hint (short first delay, longer after dismissal).
- `progress.ts` — frames-collected progress estimation and fountain-overhead model.
- `send-settings.ts` — canonical tx settings lists; the sender's dropdowns and the no-signal advice both render from it.
- `snippet.ts` — text-snippet container type.
- `dialog.ts` — geometric backdrop-click close for `<dialog>`.
- `share-dialog.ts` — the share dialog both home and sender carry (QR + copy + OS sheet).
- `status-line.ts`, `wake-lock.ts`, `format.ts`, `style.css`.

## Build plugins (`build/`)

One file each, exact-match string surgery that **throws when it misses** — markup drift breaks the build instead of shipping broken output.

- `html-tokens.ts` — `%TOKEN%` substitution (site URL, settings options, version, build id).
- `root-pwa-head.ts` — owns the manifest link and SW registration on every page; validates the URLs resolve to the site root under any subpath.
- `rewrite-standalone-links.ts` — strips/rewrites hosted-site references for the single-file builds.
- `inline-codec-wasm.ts`, `use-inline-variants.ts` — inline the decoder wasm/worker for standalone.
- `standalone-csp.ts`, `emit-as.ts` — standalone CSP and output naming.
- `license-banner.ts` — prepends the version/license/source banner to every built artifact.
- `diagnostics-endpoint.ts` — dev-only `/__diagnostics` collector behind `npm run diagnostics` (see [Diagnostics](diagnostics.md)).
- `make-icons.ts` — regenerates `public/` icons from the logo (`npm run icons`, needs librsvg).
- `benchmarks.ts` — promotes captured diagnostics runs to benchmark records and renders the README "Measured speed" section from `benchmarks/records.json` (see [Diagnostics](diagnostics.md)).

## Vendored decoder (`vendor/decimen-codec/`)

The compiled decode engine — a QR-only zxing-cpp build with a tracked fast
path, released separately as
[decimen-codec](https://github.com/bashalarmistalt/decimen-codec). The
artifacts self-identify (banner + `version()`/`build()` exports); licensing
in `NOTICE.md` alongside them.

Typechecking: `tsconfig.json` covers the pages and `shared/`; `tsconfig.node.json` covers `build/` and `vite.config.ts` (both run in `npm run build`).

## Second sender (`python-sender/`)

A sender for the same wire format in Python, so the sending half works on a
machine with no Node on it. One pygame window: a hand-drawn control panel
beside the QR stream, frames produced by a twelve-worker process pool because
encoding is 92% of the per-frame cost.

It ports the **sending** half of `shared/` — `protocol.ts`, `fountain.ts`,
`frame-capacity.ts`, `snippet.ts` — plus `send/qr-frame.ts` (segno, same pinned
mask and version locking) and `shared/qr-raster.ts`. No decoder, and
deliberately not `dlog`/`solitonCdf`/`frameIndices`: those are the v1
robust-soliton stream, unemitted since wire v2.

**Three implementations, one wire format.** `python-sender/tests/` holds a
conformance test against the golden vectors and a round trip through the real
TypeScript decoder; `python-receiver/tests/` holds the mirror of both, plus a
group that calls the two Python copies of the shared primitives side by side —
they are standalone folders, so nothing else stops them drifting apart. None of
it runs in CI, by choice — run them by hand after touching `fountain.ts`,
`protocol.ts` or `frame-capacity.ts`, because a drift there raises no exception
anywhere; the transfer just never completes.

## Second receiver (`python-receiver/`)

A receiver that reads the stream off a **screen region** rather than through a
camera: the user drags a rectangle, a background thread grabs it and decodes
whatever is inside, and the pygame window only reads snapshots and draws. It
ports the **receiving** half of `shared/` — `protocol.ts`, `fountain.ts`,
`frame-capacity.ts` — with no encoder and no camera path.

Capture is Quartz behind a one-method interface (`ScreenRegion`: a rectangle in
points → an RGB array), which is the seam a Windows or Linux backend slots into
without touching decode, window or fountain.

**Citrix is a picture-quality case, not a code path.** The receiver never learns
what is underneath the region. It matters only because HDX encodes moving
regions as H.264 and never reaches its sharp stage on an endless carousel, so
the receiver measures px/module and recommends the *sender* settings that would
survive it — in both directions, since the same measurement says when there is
margin to spend as well as when there is none.
