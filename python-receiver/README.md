# Decimen receiver, in Python

The receiving half of the same optical protocol as [decimen.app](https://decimen.app/),
straight off a **screen region**. You drag a rectangle the way `Cmd+Shift+4`
does, and whatever plays inside it gets decoded — a local sender, a video, a
virtual machine, a Citrix session. The receiver never asks what is underneath.

It exists for the case a camera cannot serve: a file that has to come **out of
a remote session** onto the machine in front of you, where the only channel
left is the screen itself.

## Run it

```bash
uv sync
uv run decimen-receive
```

Press **Space**, drag a rectangle around the QR stream, and watch it arrive.
Copy this folder anywhere and the two commands still hold: `uv.lock` pins every
dependency and `uv` fetches its own interpreter rather than trusting whatever
`python3` is on `PATH`.

**Screen Recording permission is a prerequisite**, not a nicety. Without it
macOS hands back the desktop and your own windows and hides everything else —
a capture that looks black rather than failing. The receiver checks on startup
and says so. Grant it in System Settings › Privacy & Security › Screen
Recording, to the program that actually runs (your terminal, or the `uv`-managed
Python), then relaunch — macOS does not activate it live.

Command-line arguments are shortcuts into the same window, not a second
headless mode:

```bash
uv run decimen-receive --region 100,80,900,900   # skip the drag, start there
uv run decimen-receive --out ~/Downloads         # open the save panel there
```

The region stays re-draggable with Space while a transfer runs, and `--out`
only changes where the save panel opens.

### While it runs

The sidebar carries the numbers that matter: **catch rate** (useful frames per
second — new, non-redundant), **throughput** and **time left**, **px / module**
with the error-correction level read off the code itself, the stream's `K`,
block length, layout and compression, and the file's size as soon as the header
arrives.

**px / module is the number the whole thing turns on.** It is capture width
divided by the module count, and it decides whether compression between the
sender and you can eat a code. Below the threshold the receiver names the
sender setting that would fix it; comfortably above it, it names the setting
that would carry more. Both directions come off the same measurement, and both
only speak when there is something to say.

## Through Citrix

Citrix is not a mode here — there is no Citrix code path, and the receiver
never learns it is looking at one. It matters for one reason: HDX encodes moving
regions as H.264 and only sharpens them once the motion stops, and an endless
QR carousel never stops. So the picture is worse than pixel-exact, and the
receiver's job is to notice and to say which **sender** settings would survive
it, because the compression itself is not yours to change.

Measured through a real session: the sender's defaults (60 fps, 2953 bytes, ECC
L, one code, 900 px) come out at **4 px/module** and the file arrived
SHA-256-verified. Raising the sender's display size to 1200 px is the one
setting that buys margin without touching anything else — it lifts the same
stream to 6 px/module. Sizes in between do nothing: the sender scales in whole
modules, so the useful values sit on plateaus.

## What it is and is not

**Receives** files and text snippets off a screen region, live, with progress,
statistics and a save dialog. SHA-256 is verified before anything is offered;
a mismatch is reported, not saved.

**Does not send.** That is [`python-sender/`](../python-sender/README.md).

**No camera.** The web app at [decimen.app/receive](https://decimen.app/receive/)
is the camera receiver; this one reads the screen.

**No localisation** — the interface is English, like the sender.

## Held to the wire

`docs/technical/golden-vectors.md` in the repo root is the contract, including
its **Fountain carousel** section.

```bash
uv run python tests/test_conformance.py    # 223 checks, no npm needed
uv run python tests/test_engine.py         # the capture/decode thread
uv run python tests/test_app.py            # window logic that needs no window
uv run python tests/smoke_window.py        # the whole window over a fake region
uv run python tests/ts_roundtrip.py        # against the real TypeScript encoder
```

**The conformance test does not run in CI — deliberately.** Run it by hand
after any change to `shared/fountain.ts`, `shared/protocol.ts` or
`shared/frame-capacity.ts`. Those three files are the wire format, and this
folder is a third implementation of them; a drift there raises no exception,
the transfer simply never completes.

It also checks **both** Python copies against each other. `python-sender/` and
`python-receiver/` are standalone by design, so `fnv1a`, `splitmix32`,
`frame_seed`, `frame_composition`, `block_length` and the container constants
exist twice. `test_the_two_python_copies_agree` calls them side by side —
nothing else stops the two folders drifting apart. `python-sender/` is a
sibling, not a dependency: copied away on its own, this folder still runs and
the groups that need both copies say they were skipped.

`ts_roundtrip.py` is the only test that needs `npm install` in the repo root,
because it encodes with the actual TypeScript modules rather than a
reimplementation. That is a development dependency. Running the receiver never
needs Node.

## Speed, and where the ceiling is

One background thread grabs and decodes; the window only reads snapshots and
draws, so a slow draw never throttles the catch rate. No process pool — the
sender needs one, this side does not.

| | measured |
|---|---|
| region grab (Quartz, 740 pt) | ~120 /s |
| QR decode, one code at 1200 px | 99–319 /s |
| sender's ceiling | 60 fps × 2953 B = 176 kB/s |
| real transfer, pixel-exact | ~120 kB/s |

**The decoder is never the bottleneck.** A transfer is bound by how many
distinct frames the screen actually shows and how many of them an unsynced grab
catches — roughly 41 of 60 in practice. The one lever that multiplies past that
is the sender's grid, and it is also the one that collapses over compression.

Large files hold no surprises: peak memory is a flat 4.1× the file (solved
blocks, the assembled container, the inflated file, plus frames waiting to be
peeled), so 260 MB at the container's own 64 MB ceiling. The worst single
peeling cascade costs 103 ms, which is six missed grabs the fountain hands out
again anyway.

## Platforms

**macOS** is what this was built and accepted on, including through Citrix.
Capture is Quartz `CGWindowListCreateImage` — deprecated since macOS 14, still
working on 26.5.2, and it returns physical pixels, which is what module size
needs. `ScreenCaptureKit` is the upgrade path.

**Windows and Linux** are prepared as structure, not as code: capture sits
behind `ScreenRegion` (a rectangle in points → an RGB array), so a backend can
be added without touching decode, window or fountain. `dxcam` fits that shape
on Windows and `mss` on X11; Wayland does not, because its portal hands out a
stream of a source the *user* picks, which changes region selection rather than
capture.

## Layout

```
decimen/
  protocol.py        frame header, container, SHA-256, gzip with an overflow guard
  fountain.py        the carousel and LTDecoder — receive half only
  frame_capacity.py  how much payload fits at a given frame size
  capture.py         ScreenRegion: a rectangle in points -> an RGB array
  select_region.py   the drag, on a frozen full-screen still
  engine.py          the capture-and-decode thread
  send_settings_hint.py  what to tell the sender, in both directions
  ui.py              hand-drawn controls; pygame has none
  app.py             the window and the loop
tests/
  test_conformance.py, ts_roundtrip.py, ts-encode.mjs
  test_engine.py, test_app.py, smoke_window.py
```

The module names mirror `shared/` and `receive/` in the repo root on purpose:
the implementations are meant to be read side by side, because they have to
agree byte for byte forever.

Deliberately **not** ported: the encoder half of `fountain.ts` and the camera
path. A receiver needs neither.
