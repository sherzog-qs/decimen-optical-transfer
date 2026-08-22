"""Decimen optical transfer — sender.

A file or text snippet as a fountain-coded stream of animated QR codes,
wire-compatible with decimen.app. The modules mirror the TypeScript in
shared/ and send/ closely enough that the two can be read side by side;
docs/technical/golden-vectors.md is the contract both are held to.

Importable, but without a promise: the signatures may change.
"""

import os

# Before anything pulls pygame in. It greets stdout on import, which is fine in
# a game and noise in a command-line tool that also prints its own errors there.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
