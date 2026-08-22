"""python -m decimen — the receiver.

Import inside the guard: macOS spawns nothing here (no process pool), but the
same discipline as the sender keeps startup cheap and imports honest.
"""

import sys

if __name__ == "__main__":
    from .app import main
    sys.exit(main())
