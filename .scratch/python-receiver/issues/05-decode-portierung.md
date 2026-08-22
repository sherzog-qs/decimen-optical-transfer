# Decode-Hälfte nach Python portieren und gegen die Vektoren festnageln

Type: task
Status: resolved
Blocked by: 02

## Question

Die Empfangsseite von `shared/` und `receive/` in Python, mit dem
Konformitätstest, der sie festnagelt. Keine Aufnahme, kein Fenster — dieses
Ticket endet mit „aus einer Folge gepackter Frames fällt die Datei
SHA-256-verifiziert heraus".

Zu portieren (Decode-Hälfte):

- `shared/fountain.ts` → `LTDecoder` (`addFrame`, `isComplete`, `assemble`,
  die Redundanz-Zählung), plus die geteilten `frame_seed`, `splitmix32`,
  `frame_composition`/`repair_indices`. Die geteilten Teile liegen bereits in
  `python-sender/decimen/` — hierher kopieren (standalone, siehe Karte), nicht
  importieren.
- `shared/protocol.ts` → `parseFrame`, `classifyFrame`, `frameVerdictMessage`
  (die kodierten Verdikte), `streamIdentity`, `unpackFile`, `verifyFile`,
  gunzip mit Größendeckel. **Ohne** die Sender-Seite (`packFrame`,
  `packFile`).
- `shared/frame-capacity.ts` nur soweit der Decoder es braucht.

Der Konformitätstest nutzt dieselbe Vektorquelle wie der Sender
(`docs/technical/golden-vectors.md`, Abschnitt „Fountain carousel", und
`tests/protocol.test.ts`). Er prüft mindestens: die Klassifizierungsvektoren
(magic, Version, Flags, Selbstkonsistenz) aus `golden-vectors.md`; die
Stream-Identität; einen **Round-Trip gegen den Python-Sender** — dessen
`LTEncoder` erzeugt Frames, dieser `LTDecoder` rekonstruiert sie, über
Frame-Verlust; und einen Round-Trip **gegen den TypeScript-Encoder**, damit
sich die beiden Implementierungen wirklich begegnen.

Wichtig für die gunzip-Seite: `DecompressionStream('gzip')` und Pythons `gzip`
akzeptieren beide gültige Ströme, aber der Größendeckel gegen die
attacker-kontrollierte Trailer-Länge muss nachgebaut werden
(`shared/protocol.ts:170`), sonst kann ein 80-KB-Strom vorgeben, klein zu
sein, und zu Gigabytes aufblähen.

Erledigt, wenn der Test grün ist. Der echte Beleg — durch Citrix — kommt beim
Empfänger-Fenster und der Verpackung.

## Answer — portiert und dreifach festgenagelt

Die Empfangsseite von `shared/` liegt in `python-receiver/decimen/`, und der
Konformitätstest hält sie an drei Ebenen fest.

### Was liegt

```
python-receiver/decimen/
  protocol.py       parse_frame, classify_frame, frame_verdict_message,
                    stream_identity, unpack_file, verify_file, gunzip,
                    plus die geteilten fnv1a/splitmix32/32-Bit-Ops
  fountain.py       LTDecoder (Peeling-Kaskade), frame_composition — Decode-Hälfte
  frame_capacity.py aus dem Sender kopiert (standalone)
  capture.py        die ScreenRegion-Schnittstelle (aus Ticket 01)
  select_region.py  die Auswahl-Geste (aus Ticket 04)
tests/
  test_conformance.py   167 Prüfungen, 8 Gruppen
  ts_roundtrip.py       gegen den TypeScript-Encoder
  ts-encode.mjs         die Node-Hälfte davon
```

Kein Encoder, kein `dlog`/`solitonCdf`/`frameIndices` — alles drei gehört
nicht in einen Empfänger.

### Die drei Ebenen

1. **167 Prüfungen gegen die Golden Vectors** (`test_conformance.py`): das
   kanonische Frame parst byte-genau; die Klassifizierungsvektoren aus
   `golden-vectors.md` (fremd, älterer/neuerer Sender, unbekannte kritische
   Flags, missgebildet) inklusive der Verdikt-Wortlaute; Selbstkonsistenz;
   Stream-Identität mit der Trennzeichen-Kollision; der Container-Round-Trip
   gegen den **Python-Sender** (Datei, gzip, Schnipsel); und der
   gunzip-Overflow-Schutz gegen die attacker-kontrollierte Trailer-Länge.
2. **Python↔Python** über 15 % Frame-Verlust: der `LTEncoder` des Senders
   erzeugt Frames, dieser `LTDecoder` baut die Datei zurück, SHA-256 stimmt,
   Overhead unter 1,3×. Die beiden Python-Hälften begegnen sich.
3. **Der Begegnungspunkt mit TypeScript** (`ts_roundtrip.py`): der
   **TypeScript-Encoder** aus `shared/` erzeugt 267 Frames über 15 % Verlust,
   der Python-Empfänger rekonstruiert den Container, entpackt die Datei,
   verifiziert SHA-256. Genau der Encoder, den ein Handy oder die Web-App
   fährt.

### Zwei Fallen beim Bauen

**Namenskonflikt der beiden `decimen`-Pakete.** Sender und Empfänger haben
beide ein Paket namens `decimen`; den Sender einfach auf `sys.path` zu legen,
überschattet das eigene. Der Test lädt den Sender deshalb als separaten
Paketbaum (`sender_decimen.*`) über `importlib`, statt sich auf die
Pfadreihenfolge zu verlassen.

**Zweimal falsche Testdaten.** `bytes(range(256))*4` gzippt der Sender (Muster),
und ein LCG erzeugt komprimierbare niederwertige Bits — beide Male wollte der
Test den unkomprimierten Pfad prüfen und bekam gzip. Jetzt SHA-256-Kette bzw.
`crypto.getRandomValues`, also echt inkompressibel.

### Was fehlt

Der echte Beleg — ein Strom **durch Citrix** — kommt beim Empfänger-Fenster
und der Verpackung. Der Test beweist die Bytes, nicht die Optik über den
Kanal.
