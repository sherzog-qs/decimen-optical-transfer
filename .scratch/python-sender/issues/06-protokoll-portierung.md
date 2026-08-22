# Protokoll nach Python portieren und gegen die Vektoren festnageln

Type: task
Status: resolved
Blocked by: 01, 03

## Question

Der Sende-Pfad von `shared/` in Python, mit dem Konformitätstest, der ihn
festnagelt. Kein Fenster — dieses Ticket endet mit „ein Handy auf
decimen.app empfängt Frames, die Python erzeugt hat".

Zu portieren ist ausschließlich die Sendeseite:

- `shared/fountain.ts` → `frameSeed`, `splitmix32` (liegt in `protocol.ts`),
  `repairIndices`, `frameComposition`, `cycleLength`, `LTEncoder`. **Ohne
  Decoder, und ohne `dlog`/`solitonCdf`/`frameIndices`** — die sind der
  v1-Soliton-Strom und werden seit wire v2 nicht mehr gesendet. Alles
  32-Bit-Ganzzahlarithmetik, in Python mit `& 0xFFFFFFFF`. Achtung bei
  `repairIndices`: JS-`Set` bewahrt die Einfügereihenfolge, Pythons `set`
  nicht — für den XOR gleichgültig, für einen Vergleich der Indexliste nicht.
  **Der Fountain-Teil ist bereits erledigt und verifiziert:** siehe Asset
  `.scratch/python-sender/assets/carousel-conformance.py`, das alle vier
  goldenen Stromhashes reproduziert. Von dort übernehmen, nicht neu schreiben.
- `shared/protocol.ts` → `packFrame`, Container-Bau, SHA-256,
  gzip-Schwelle, `MAX_FILE_BYTES`. **Ohne** `parseFrame` und Verifikation.
- `shared/frame-capacity.ts` → Kapazitätsrechnung, `MAX_SOURCE_BLOCKS`.
- `shared/snippet.ts` → Textschnipsel-Container.
- `send/qr-frame.ts` → mit der in Ticket 01 gewählten Bibliothek.
- `shared/qr-raster.ts` → Modulmatrix zu Pixeln.

Der Test prüft mindestens: das kanonische Frame aus `golden-vectors.md`
byte-genau, die Stream-Identität, die vier Stromfingerabdrücke aus dem
Abschnitt Fountain carousel, die QR-Fingerabdrücke, den Container byte-genau
im unkomprimierten Fall, `isPrecompressedType` gegen eine Medientyp-Tabelle,
und einen Round-Trip über 300 KB inkompressibler Daten mit Frame-Verlust —
gegen den TypeScript-Decoder, damit die beiden Implementierungen sich
wirklich begegnen und nicht nur jede für sich stimmig ist. Was byte-genau
geprüft wird und was nur im Round-Trip, legt das Vektoren-Ticket im
Einzelnen fest.

Erledigt, wenn der Test grün ist **und** ein Handy auf decimen.app einen
von Python erzeugten Stream tatsächlich dekodiert hat. Der Test allein
genügt nicht — genau diese Lücke schließt der Feldversuch.

## Stand — gebaut und geprüft, wartet auf den Feldversuch

Das Ticket sagt ausdrücklich: erledigt erst, wenn **ein Handy auf decimen.app
einen von Python erzeugten Strom dekodiert hat**. Der Test allein genügt nicht.
Solange das nicht passiert ist, bleibt dieses Ticket beansprucht, nicht gelöst.

### Was liegt

```
python-sender/
  decimen/
    protocol.py         Frame-Header, Container, SHA-256, gzip-Schwellen,
                        safe_file_name, is_precompressed_type, fnv1a, splitmix32
    fountain.py         frame_seed, repair_indices, frame_composition, LTEncoder
    frame_capacity.py   Kapazitätsrechnung, MAX_SOURCE_BLOCKS
    qr.py               create_frame_qr (segno), grid_dims, rasterize_qr_grid
  tests/
    test_conformance.py           425 Prüfungen, 14 Gruppen — grün
    qr-reference-fingerprints.txt die 20 QR-Referenzfälle, 782 Bytes
    ts_roundtrip.py               Round-Trip gegen den TS-Decoder — grün
    ts-roundtrip.mjs              die Node-Hälfte davon
    field_check.py                der Feldversuch, für ein Handy
```

Kein Decoder, kein `dlog`, keine Soliton-Verteilung — alles drei gehört nicht
in einen Sender.

### Was der Konformitätstest abdeckt

425 Prüfungen: das kanonische Frame byte-genau gegen den Hex aus
`golden-vectors.md`; Stream-Identität inklusive der Trennzeichen-Kollision
`{k=1, blockLen=23}` gegen `{k=12, blockLen=3}` und beider Flag-Hälften; die
vier Fountain-Stromfingerabdrücke; die strukturellen Karussell-Regeln über vier
k-Werte; dass jeder Frame exakt `blockLen` Bytes ist, auch der über dem kurzen
Schwanzblock; den Container byte-genau an jedem deklarierten Offset; beide
gzip-Schwellen in beide Richtungen; `is_precompressed_type` gegen 28
Medientypen; `safe_file_name` gegen Pfade, Steuerzeichen und U+FEFF; die
Kapazitätsrechnung; Geometrie und Version aller 20 QR-Referenzfälle plus die
drei vergleichbaren Matrix-Fingerabdrücke; und dass die erzeugten Codes zur
Quellbytefolge zurück dekodieren.

### Der Begegnungspunkt

`ts_roundtrip.py` fährt 300 KB inkompressibler Daten durch Container →
Fountain → Frames, verwirft deterministisch 15 % davon und lässt **den
TypeScript-Decoder aus `shared/`** rekonstruieren — `parseFrame`, `LTDecoder`
und `unpackFile`, nichts nachgebaut:

```
Container 307283 B, k=105, blockLen=2931
267 Frames gesendet, 48 verworfen (15% Verlust)
TypeScript-Decoder: 118 Frames akzeptiert, 0 abgelehnt
jedes Byte identisch · SHA-256 stimmt · Overhead 1.12x
```

Der Empfänger lernt alles aus den Frames — `k`, `blockLen`, `sessionId`,
`totalLen` kommen aus dem ersten geparsten Header, kein Handshake.

Braucht `npm install` im Repo-Wurzelverzeichnis. Das ist eine Entwicklungs-,
keine Laufzeitabhängigkeit: den Sender zu betreiben braucht nie Node.

### Zwei Testfehler, die keine Codefehler waren

Der Vollständigkeit halber, weil beide danach aussahen: `grid_dims(3)` und
`grid_dims(8)` sind **gültig** (1×3 und 2×4 füllen ihr Rechteck) — der
TypeScript akzeptiert sie genauso, meine Erwartung war falsch. Und mein erstes
„inkompressibles" Testdatum war eine arithmetische Folge, in der gzip sehr wohl
Struktur findet; es ist jetzt eine SHA-256-Kette.

### Was noch fehlt

**Der Feldversuch.** `tests/field_check.py` öffnet ein pygame-Fenster und
streamt einen echten, von Python erzeugten Karussell-Strom:

```
cd python-sender
uv run python tests/field_check.py                 # ein Textschnipsel
uv run python tests/field_check.py bericht.pdf     # eine Datei
```

Auf dem Handy `https://decimen.app/receive/` öffnen und draufhalten. Kommt der
Text beziehungsweise die Datei SHA-256-verifiziert heraus, ist dieses Ticket
gelöst und die Zeile gehört in die Decisions-so-far der Karte.

### Nachtrag: `uv run` ging nicht

Der erste Anlauf des Feldversuchs scheiterte an `ModuleNotFoundError: No module
named 'segno'`. Ursache: `python-sender/` hatte keine `pyproject.toml`, also
fand `uv run` kein Projekt und installierte nichts. Der Befehl war nie erprobt
worden — nur der Umweg über ein Scratch-venv.

Behoben mit dem Minimum, das den Feldversuch möglich macht: `pyproject.toml`
mit den drei Laufzeitabhängigkeiten (segno, pygame-ce, pillow), `zxing-cpp` als
Entwicklungsgruppe, `package = false` (decimen wird importiert, nicht gebaut),
`.python-version` auf 3.13 — und `python-preference = "only-managed"`, weil
Homebrews python@3.13 kein tkinter mitbringt. Bestätigt: die so entstandene
Umgebung hat Tk 9.0.

`.venv/` steht jetzt in der `.gitignore` des Repos.

**Startbefehl, CLI-Einstiegspunkt und README bleiben bei "Verpackung: uv,
Startbefehl, CLI, README".** Diese `pyproject.toml` ist die Krücke für den
Feldversuch, nicht die fertige Verpackung.

Ausserdem entschärft: der Feldversuch lief mit 1465 Bytes je Frame und
Skalierung 4, was den 169-Byte-Schnipsel in einen Version-27-Code presste —
unnötig dicht für die Frage „sieht ein Handy das überhaupt". Vorgaben jetzt 500
Bytes und Skalierung 6, also ein Version-15-Code mit rund 510 Pixeln Kante.

Beide Befehle sind jetzt erprobt:

```
cd python-sender
uv run python tests/test_conformance.py    # 425 Prüfungen
uv run python tests/field_check.py         # das Fenster für das Handy
```

## Answer — Feldversuch bestanden

Ein Handy auf `https://decimen.app/receive/` hat einen von Python erzeugten
Strom vom Bildschirm gelesen und den Schnipsel SHA-256-verifiziert ausgepackt:

> Sent from Python over light. If you can read this, the port is wire-
> compatible with decimen.app: same fountain carousel, same frame header, same
> container, same SHA-256.

Bedingungen: `tests/field_check.py` mit den Vorgaben — 500 Bytes je Frame,
ECC L, Skalierung 6, 20 fps, ein einzelner Code, QR-Version 15, Container
169 Bytes, k=1, unkomprimiert.

Damit ist die Lücke geschlossen, die der Konformitätstest offen lässt. Der
TypeScript-Decoder hatte gezeigt, dass die **Bytes** stimmen; der Feldversuch
zeigt, dass die **Optik** stimmt — Modulgröße, Kontrast, Bildrate und
Autofokus einer echten Kamera.

Was damit belegt ist, in der Reihenfolge der Beweiskraft:

1. 425 Prüfungen gegen die goldenen Vektoren — Python stimmt mit den
   aufgezeichneten Konstanten überein.
2. Round-Trip gegen `parseFrame`, `LTDecoder` und `unpackFile` aus `shared/`
   über 15 % Frame-Verlust — die beiden Implementierungen stimmen miteinander
   überein, nicht nur jede für sich.
3. Ein Handy mit einer Kamera — es funktioniert im Feld.

Ticket erledigt.
