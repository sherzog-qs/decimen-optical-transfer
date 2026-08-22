# Decode-Hälfte nach Python portieren und gegen die Vektoren festnageln

Type: task
Status: open
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
