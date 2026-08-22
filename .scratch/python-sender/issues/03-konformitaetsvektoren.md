# Woher bekommt der Python-Test seine Fountain-Vektoren?

Type: grilling
Status: resolved

## Question

Der Konformitätstest ist Pflicht (Charting-Session Q12), aber ein Teil der
nötigen Vektoren liegt nur in ausführbarem TypeScript.

Die Lage:

- `docs/technical/golden-vectors.md` ist bereits eine Spezifikation für
  Nicht-TypeScript-Clients: Header-Hex, Klassifizierungsregeln,
  Stream-Identität, Round-Trip-Kriterien. Das ist ohne npm lesbar und deckt
  die Frame-Ebene ab.
- Die **Fountain-Interna** decken es nicht ab: `dlog()`-Werte,
  `solitonCdf(k)`, die von `frameIndices(k, cdf, sessionId, seq)` gelieferten
  Blockindizes. Die stehen nur in `tests/fountain.test.ts`. Genau dort sitzt
  aber das Desynchronisationsrisiko (siehe Karte, Notes).

Zu entscheiden: (a) einmalig mit Node eine JSON-Fixture erzeugen und
einchecken — der Python-Test liest sie danach ohne npm, aber jemand muss den
Generator pflegen; (b) die Werte von Hand aus dem TS-Test in die Fixture
übertragen — kein Generator, aber Abtippfehler sind stumme Wire-Fehler;
(c) `docs/technical/golden-vectors.md` um einen Fountain-Abschnitt
erweitern, so dass die Vektoren dort normativ stehen, wo schon steht, woran
ein zweiter Client gemessen wird.

Zweitens zu klären: **gzip lässt sich nicht byte-genau vergleichen.** Der
Container komprimiert im Web mit `CompressionStream('gzip')`, in Python mit
`gzip`/`zlib` — beide erzeugen gültige, aber verschiedene Bytes. Der Test
kann für komprimierte Nutzlasten also nur den Round-Trip prüfen, nicht die
Bytes. Die Schwelle dagegen (`compressed.length + 64 < bytes.length`,
`shared/protocol.ts:284`) muss exakt nachgebaut werden, sonst weicht das
`flags`-Feld ab. Die Antwort hält fest, was byte-genau geprüft wird und was
nur im Round-Trip.

## Answer

### Der Fund, der die Frage neu stellt

`dlog`, `solitonCdf` und `frameIndices` sind **der v1-Soliton-Strom und werden
seit wire v2 nicht mehr gesendet** (`tests/fountain.test.ts:4`, bestätigt durch
`grep`: kein Aufrufer außerhalb der Tests, in keiner Datei).
`LTEncoder.encode()` ruft ausschließlich `frameComposition()` — systematischer
Sweep über `k` Blöcke, danach Reparaturframes mit gleichverteiltem Grad 4–24.

Damit fällt das Risiko weg, um das die Karte herum gebaut war. Der Sender
braucht **keine einzige Gleitkommaoperation**: `frameSeed`, `splitmix32`,
`repairIndices`, `frameComposition` sind durchweg 32-Bit-Ganzzahlarithmetik.

### Vektorquelle: die vier goldenen Stromhashes, abgeschrieben

`tests/fountain.test.ts:182` pinnt den Strom nicht als Wertetabelle, sondern
als **FNV-1a über 64 verkettete Frames**, für vier Parametersätze:

| k | blockLen | sessionId | fnv1a |
|---|---|---|---|
| 1 | 64 | 1 | `0xf6a115c5` |
| 23 | 64 | 7 | `0x4a5d3eaa` |
| 179 | 2933 | 4242 | `0x54f78d05` |
| 716 | 1445 | 65535 | `0x75b73b85` |

Ein Hash deckt `frameSeed`, `splitmix32`, den Reparatur-Zug, das Block-Padding
und die XOR-Reihenfolge gemeinsam ab. Kein Generator, keine Fixture-Datei, kein
Node — vier Konstanten plus die Formel für `testPayload`.

Der Einwand aus dem Ticketkörper („Abtippfehler sind stumme Wire-Fehler") war
falsch und wird hier ausdrücklich zurückgenommen: bei vier Hashes ist ein
Tippfehler ein **lauter** Testfehler.

**Verifiziert, nicht behauptet.** Der Python-Nachbau reproduziert alle vier
Hashes bit-genau, inklusive k=716 mit sessionId 65535, und erfüllt die
strukturellen Regeln des Karussells aus `tests/fountain.test.ts:306`. Siehe
Asset `carousel-conformance.py`. Ein Stolperstein dabei: JS-`Set` bewahrt die
Einfügereihenfolge, Pythons `set` nicht — `repairIndices` braucht ein `dict`
oder eine Liste, sonst weicht die Indexreihenfolge ab. Für den XOR ist das
gleichgültig, für einen Vergleich der Indexliste nicht.

Die Werte stehen ab jetzt zusätzlich normativ in
`docs/technical/golden-vectors.md`, Abschnitt **„Fountain carousel"** — mit
Karussell-Regel, Pseudocode für beide Generatoren, dem Block-Padding und den
vier Fingerabdrücken. Dort, wo die Seite ohnehin sagt, woran ein zweiter Client
gemessen wird.

### QR-Referenz: auf Fingerabdrücke eingedampft

Die 82 KB Rohmatrizen aus „QR-Encoder in Python" sind ersetzt durch
`qr-reference-fingerprints.txt` — **782 Bytes**, 20 Zeilen mit Fall, Version,
Größe, FNV und einer Spalte `matrixgleich`.

Die letzte Spalte ist nötig, weil segno und npm `qrcode` nur in drei der
zwanzig Fälle dieselbe Matrix erzeugen (dort, wo die Nutzlast die Kapazität
exakt füllt). Für alle übrigen gilt: Version und Größe müssen stimmen, die
dekodierten Bytes müssen der Quelle entsprechen, die Matrix wird nicht
verglichen. `qr-conformance-sweep.py` ist entsprechend umgeschrieben und läuft
jetzt **ohne npm** — 20/20 in Ordnung.

### gzip: was byte-genau geprüft wird und was nicht

gzip tauscht nur den Nutzlastbereich des Containers. Byte-genau prüfbar sind
daher **alle Kopffelder und der ganze unkomprimierte Fall**: Magic, Flag-Byte,
Name- und Typlängen, `fileLength`, `transmittedLength`, SHA-256 der
**Originalbytes**, Name- und Typbytes. Ein Testfall bleibt unkomprimiert, wenn
er unter 768 Bytes liegt oder einen vorkomprimierten Medientyp trägt.

Für komprimierte Nutzlasten wird **nur die Entscheidung und der Round-Trip**
geprüft, nicht die Bytes: `CompressionStream('gzip')` und Pythons `gzip`
erzeugen beide gültige, aber verschiedene Ströme. Eine Größendifferenz
verschiebt `transmittedLength` und damit `payloadFnv` — kein
Kompatibilitätsbruch, der Empfänger lernt alles aus den Frames, aber eben nicht
byte-vergleichbar.

Zwei Schwellen müssen exakt nachgebaut werden, sonst driftet das Flag-Byte:

- `tryGzip = bytes.length >= 768 && !isPrecompressedType(type)`
- `useGzip = compressed.length + 64 < bytes.length` (`shared/protocol.ts:284`)

**`isPrecompressedType()` wird mitgepinnt** — gegen eine Medientyp-Tabelle, die
die drei Regeln abdeckt (OOXML-Präfix, OpenDocument-Präfix, `+zip`-Suffix) plus
die `PRECOMPRESSED_TYPES`-Liste. Sonst schickt TS eine Datei roh, die Python
komprimiert: kein Bruch, aber eine Verhaltensdrift, die sonst niemand bemerkt.

### Node im Test ja, im Betrieb nein

Der Python-Test braucht nach dieser Entscheidung **kein Node** — weder für die
Fountain- noch für die QR-Vektoren. Der Round-Trip gegen den **TypeScript-
Decoder** aus „Protokoll nach Python portieren" braucht es weiterhin, und das
bleibt so: ohne mindestens einen echten Begegnungspunkt der beiden
Implementierungen ist „wire-kompatibel" eine Behauptung. „Ohne npm" ist eine
Eigenschaft des Betreibens, nicht des Entwickelns.

### Assets

- `.scratch/python-sender/assets/carousel-conformance.py` — der verifizierte
  Python-Nachbau des Karussells gegen die vier Hashes. Die Vorlage für den
  Fountain-Teil in „Protokoll nach Python portieren".
- `.scratch/python-sender/assets/qr-reference-fingerprints.txt` — 782 Bytes
  statt 82 KB.
- `.scratch/python-sender/assets/qr-conformance-sweep.py` — npm-frei
  umgeschrieben.
