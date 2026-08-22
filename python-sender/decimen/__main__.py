"""python -m decimen — the sender.

The console-script entry point and CLI arguments belong to the packaging
ticket; this is the plain way in.
"""

import multiprocessing
import sys

if __name__ == "__main__":
    # Import inside the guard, not at module level. macOS spawns worker
    # processes by re-importing this module, and a top-level `from .app import
    # main` would drag pygame and the whole panel into all twelve of them —
    # paid for on every stream restart, for code no worker ever calls.
    multiprocessing.freeze_support()
    from .app import main

    sys.exit(main())
