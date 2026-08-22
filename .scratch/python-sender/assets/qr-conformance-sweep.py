"""QR-Konformitaet ohne npm: segno gegen die eingecheckten Fingerabdruecke.

Prueft je Fall drei Dinge:
  1. Version und Groesse stimmen mit dem TS-Pfad ueberein (das fordert das Tiling).
  2. Wo die Matrizen ueberhaupt gleich sein koennen (matrixgleich=ja), stimmt
     auch der Fingerabdruck.
  3. Die eigene Matrix dekodiert zur Quellbytefolge zurueck (selbstpruefend).

Braucht: segno, zxing-cpp, pillow. Der Sender selbst braucht nur segno.
"""
import pathlib, sys, time
import segno, zxingcpp
from PIL import Image

PINNED_MASK, QUIET = 4, 4
M32 = 0xFFFFFFFF

def imul(a, b):
    r = (a * b) & M32
    return r - 0x100000000 if r & 0x80000000 else r

def fnv1a(data):
    h = 0x811C9DC5
    for byte in data:
        h ^= byte
        h = imul(h, 0x01000193) & M32
    return h & M32

def frame_bytes(n):
    b = bytearray((i * 37 + 11) & 0xFF for i in range(n))
    b[0:4] = bytes((0xD1, 0xC3, 3, 0x00))
    return bytes(b)

def make(data, ecc, version):
    # boost_error=False ist Pflicht: sonst hebt segno die ECC-Stufe eigenmaechtig an.
    return segno.make(data, mode="byte", error=ecc, version=version,
                      mask=PINNED_MASK, boost_error=False)

def matrix_bits(qr):
    bits = [1 if m else 0 for row in qr.matrix for m in row]
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for j, bit in enumerate(bits[i:i + 8]):
            v |= bit << (7 - j)
        out.append(v)
    return bytes(out)

def to_img(qr, scale=3):
    n = len(qr.matrix)
    side = (n + 2 * QUIET) * scale
    img = Image.new("L", (side, side), 255)
    px = img.load()
    for y, row in enumerate(qr.matrix):
        for x, m in enumerate(row):
            if m:
                for dy in range(scale):
                    for dx in range(scale):
                        px[(x + QUIET) * scale + dx, (y + QUIET) * scale + dy] = 0
    return img

def decode(img):
    r = zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode,
                               binarizer=zxingcpp.Binarizer.FixedThreshold)
    return bytes(r[0].bytes) if r else None

table = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                     else pathlib.Path(__file__).with_name("qr-reference-fingerprints.txt"))
rows = [l.split() for l in table.read_text().splitlines()
        if l.strip() and not l.lstrip().startswith("#")]

failures = []
for label, version, size, fnv, comparable in rows:
    n, ecc = int(label[:-1]), label[-1]
    version, size, fnv = int(version), int(size), int(fnv, 16)
    src = frame_bytes(n)
    auto = make(src, ecc, None)
    qr = make(src, ecc, version)
    checks = []
    if auto.version != version or len(qr.matrix) != size:
        checks.append(f"Geometrie v{auto.version}/{len(qr.matrix)} statt v{version}/{size}")
    if comparable == "ja" and fnv1a(matrix_bits(qr)) != fnv:
        checks.append("Fingerabdruck")
    if decode(to_img(qr)) != src:
        checks.append("Dekodierung")
    if checks:
        failures.append((label, checks))
    print(f"{label:>7}  v{version:<3} {size:>3}²  "
          f"{'FEHLER: ' + ', '.join(checks) if checks else 'ok'}")

print(f"\n{len(rows) - len(failures)}/{len(rows)} Faelle in Ordnung")
if failures:
    sys.exit(1)

print("\n--- Tempo (segno, Maske gepinnt, Version verriegelt) ---")
for n, ecc in [(2953, "L"), (1465, "L"), (500, "L")]:
    src = frame_bytes(n)
    v = make(src, ecc, None).version
    t0 = time.perf_counter(); reps = 0
    while time.perf_counter() - t0 < 2.0:
        make(src, ecc, v); reps += 1
    print(f"{n:>5} B  v{v:<3}  {reps / (time.perf_counter() - t0):7.1f} Kodierungen/s")
