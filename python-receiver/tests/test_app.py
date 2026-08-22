"""The window logic that needs no window: the save offer and the panel numbers.

_offer only touches the snapshot, the sleep lock and save_dialog, so the app is
built with __new__ and those two are stand-ins.

    uv run python tests/test_app.py
"""
from __future__ import annotations

import pathlib
import sys
import types

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from decimen import app as a

calls = 0


def _dialog(_name):
    global calls
    calls += 1
    return None            # the user presses Cancel, every time


def _snap(file):
    return types.SimpleNamespace(complete=True, sha256_ok=True, file=file)


def test_cancel_offers_once():
    global calls
    a.plat.save_dialog = _dialog
    app = a.ReceiverApp.__new__(a.ReceiverApp)
    app._offered = None
    app.awake = types.SimpleNamespace(off=lambda: None)
    app.status = ""

    snap = _snap(types.SimpleNamespace(is_snippet=False, name="x.bin", data=b""))
    calls = 0
    for _ in range(30):                       # 30 UI frames after completion
        app._offer(snap)
    assert calls == 1, f"cancel re-opened the dialog ({calls} times)"

    app._offer(snap, force=True)              # S: same file, offered again
    assert calls == 2, "S did not re-offer the cancelled file"

    other = _snap(types.SimpleNamespace(is_snippet=False, name="y.bin", data=b""))
    app._offer(other)                         # a new stream: offered on its own
    assert calls == 3, "a second file was not offered"
    print("  cancel offers once, S re-offers, a new file offers again")


def test_panel_numbers():
    s = types.SimpleNamespace(catch_rate=20.0, block_len=1000, complete=False,
                              frames_collected=100, frames_needed=400)
    assert a.throughput_kb(s) == "20.0 kB/s", a.throughput_kb(s)
    assert a.time_left(s) == "15s", a.time_left(s)
    s.catch_rate = 2.0                     # 300 frames left at 2/s = 150s
    assert a.time_left(s) == "2m 30s", a.time_left(s)
    s.catch_rate = 0.0                     # nothing arriving: no divide, no guess
    assert a.time_left(s) == "—", a.time_left(s)
    assert a.throughput_kb(s) == "0.0 kB/s", a.throughput_kb(s)
    s.complete = True
    assert a.time_left(s) == "done", a.time_left(s)
    print("  throughput and time left, including the zero-rate case")


def test_headroom():
    from decimen import send_settings_hint as hint
    from decimen.protocol import HEADER_LEN

    # Where the field run sits: 2953 bytes, one code, 6 px/module. That is the
    # bare rescue threshold with no margin left, so nothing is recommended.
    assert hint.headroom(6.0, 2953 - HEADER_LEN, 1) is None

    # One step up in module size and a second code fits: it is a whole extra
    # ROW, not a narrower column, so it doubles the payload at unchanged
    # px/module and only costs window height.
    line = hint.headroom(9.0, 2953 - HEADER_LEN, 1)
    assert line and "--codes 2" in line and "--bytes 2953" in line, line
    assert "2.0x" in line and "taller" in line, line

    # Fat modules, small frames: a lot of margin to spend at once.
    line = hint.headroom(24.0, 500 - HEADER_LEN, 1)
    assert line and "--codes 6" in line, line

    # Nothing left to suggest, and below target the rescue line owns the slot.
    assert hint.headroom(9.0, 2953 - HEADER_LEN, 2) is None
    assert hint.headroom(4.0, 2953 - HEADER_LEN, 1) is None

    # The level is read off the code, not assumed: 1000 bytes at H needs a far
    # bigger symbol than at L, so the same measurement affords less.
    assert hint.modules_for(1000, "L") == 105 and hint.modules_for(1000, "H") == 161
    # ...so the same margin buys different settings, and at H it must never
    # name a frame a code at that level cannot carry (1273 bytes is the top).
    line = hint.headroom(14.0, 1000 - HEADER_LEN, 1, "L")
    assert line and "--bytes 2953 --codes 2" in line, line
    line = hint.headroom(14.0, 1000 - HEADER_LEN, 1, "H")
    assert line and "--bytes 500 --codes 6" in line, line
    print("  headroom: names the next setting, and shuts up when there is none")


if __name__ == "__main__":
    test_cancel_offers_once()
    test_panel_numbers()
    test_headroom()
    print("\n19 checks passed")
