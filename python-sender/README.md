# Decimen sender, in Python

A second sender for the same optical protocol as [decimen.app](https://decimen.app/):
a file or a text snippet leaves this window as a stream of animated QR codes, and
a phone pointed at the screen receives it. Same fountain carousel, same frame
header, same container, same SHA-256 — a phone running the web receiver cannot
tell the two senders apart.

It exists so the sending half works **without Node or npm on the machine**.

## Run it

```bash
uv sync
uv run decimen-send
```

That is the whole setup. Copy this folder anywhere and the two commands still
hold: `uv.lock` pins every dependency, and `uv` fetches its own interpreter
rather than trusting whatever `python3` happens to be on `PATH`.

Pick a file or write a snippet, then point a phone at
[decimen.app/receive](https://decimen.app/receive/). Dropping a file onto the
QR area works too.

Command-line arguments are a shortcut into the same window, not a second
headless mode:

```bash
uv run decimen-send report.pdf                 # opens with the file loaded
uv run decimen-send report.pdf --fps 24        # …and slower, if the phone struggles
uv run decimen-send --bytes 1465 --codes 4     # …preset, waiting for a drop
```

`--fps`, `--bytes`, `--ecc` and `--codes` only accept values the panel also
offers, so nothing reachable from the command line is unreachable from the
window.

**Frame size and error correction are not independent.** A single QR code holds
2953 bytes at L, 2331 at M, 1663 at Q and 1273 at H — so 2953 bytes / frame
only exists at L. The panel greys out the sizes that cannot work at the current
level, and raising the level drops the frame size to the largest that fits,
saying so in the status line.

## What it is and is not

**Sends** files and text snippets. Five settings — frame rate, bytes per frame,
error correction, layout and display size — adjustable while a stream runs.
Every change restarts the stream with a fresh session id, exactly as the web
sender does; only bytes-per-frame strictly has to, and matching the reference
sender beats saving the receiver's progress.

**Does not receive.** No camera, no decoder. Use the web app or a phone for
that.

**No animation export**, no localisation — the interface is English. Those live
with the web app.

## Held to the wire

`docs/technical/golden-vectors.md` in the repo root is the contract, including
its **Fountain carousel** section, which this port added because the page did
not previously cover the part where getting it wrong is silent.

```bash
uv run python tests/test_conformance.py    # 425 checks, no npm needed
uv run python tests/ts_roundtrip.py        # against the real TypeScript decoder
uv run python tests/smoke_window.py        # the window, including click paths
```

**The conformance test does not run in CI — deliberately.** Run it by hand
after any change to `shared/fountain.ts`, `shared/protocol.ts` or
`shared/frame-capacity.ts`. Those three files are the wire format, and this
folder is a second implementation of them; a drift there does not raise an
exception anywhere, it just means a transfer never completes.

`ts_roundtrip.py` is the only test that needs `npm install` in the repo root,
because it decodes with the actual TypeScript modules rather than a
reimplementation. That is a development dependency. Running the sender never
needs Node.

## Speed

Encoding is 92% of the per-frame cost, so frames are produced by a twelve-worker
process pool that hands back finished rasters. Measured on a 12P/4E machine:

| | frames/s | goodput |
|---|---|---|
| single-threaded | 62.6 | 156 KB/s |
| twelve workers | 681.9 | 1697 KB/s |

The second row is not a transfer rate — no screen shows 682 frames a second.
It means the sender is no longer the bottleneck; after that the receiver is.
For reference, the web sender is measured at 418.5 KB/s desktop-to-phone.

Sixteen workers is measurably *worse* than twelve here: the efficiency cores
drag the group down. That number is tuned for this machine and wants
re-measuring on other hardware — see `MAX_WORKERS` in `decimen/pool.py`.

## Platforms

**macOS** is what this was built and accepted on.

**Windows** is prepared and untested. pygame-ce, segno and the process pool all
work there, and Windows spawns workers the same way macOS does. The file dialog
(PowerShell/WinForms) and the sleep inhibitor (`SetThreadExecutionState`) are
written but have never run; both are wrapped, so a failure leaves drag and drop
and the ordinary screensaver rather than a crash. SF Pro is absent, so the font
stack falls through to Segoe UI.

**Linux** is not considered: no file dialog, no sleep inhibitor, and drag and
drop depends on the window manager.

## Layout

```
decimen/
  protocol.py        frame header, container, SHA-256, gzip thresholds
  fountain.py        the carousel and LTEncoder — sender half only
  frame_capacity.py  how much payload fits at a given frame size
  qr.py              QR generation (segno) and grid rasterisation
  pool.py            the worker pool and the prefetch buffer
  ui.py              hand-drawn controls; pygame has none
  app.py             the window and the loop
tests/
  test_conformance.py, ts_roundtrip.py, ts-roundtrip.mjs
  smoke_window.py, field_check.py
  qr-reference-fingerprints.txt
```

The module names mirror `shared/` and `send/` in the repo root on purpose: the
two implementations are meant to be read side by side, because they have to
agree byte for byte forever.

Deliberately **not** ported: `dlog`, `solitonCdf` and `frameIndices`. They are
the v1 robust-soliton stream and have not been emitted since wire v2. The
TypeScript keeps them because their vectors were expensive to derive; a sender
does not need them.
