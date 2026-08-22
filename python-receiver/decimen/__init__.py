"""Decimen optical transfer — receiver.

Reads the QR carousel straight off a screen region instead of through a camera,
decodes the fountain stream, and reconstructs the file — wire-compatible with
decimen.app. The receive half of shared/ and receive/, mirrored closely so the
two can be read side by side; docs/technical/golden-vectors.md is the contract.

Importable, but without a promise: the signatures may change.
"""

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
