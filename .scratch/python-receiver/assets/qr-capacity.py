"""The byte-mode capacity table in send_settings_hint.py, generated.

Binary-searches segno for the largest byte payload each version holds at each
error-correction level. Measured, not quoted — px/module follows from the
version, and the version follows from these numbers.

    uv run --with segno python .scratch/python-receiver/assets/qr-capacity.py
"""
import segno

for ecc in "LMQH":
    caps = []
    for version in range(1, 41):
        lo, hi, best = 0, 3000, 0
        while lo <= hi:
            mid = (lo + hi) // 2
            try:
                segno.make(bytes(mid), error=ecc, mode="byte", version=version)
                best, lo = mid, mid + 1
            except Exception:
                hi = mid - 1
        caps.append(best)
    print(f'    "{ecc}": ({", ".join(map(str, caps))}),')
