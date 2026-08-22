# Den Empfänger bauen

Type: task
Status: resolved
Blocked by: 03, 04, 05, 06

## Question

Die Anwendung über der portierten Decode-Hälfte: Bereich aufziehen, abgreifen,
dekodieren, Fortschritt zeigen, empfehlen, speichern.

Umfang aus den vorgelagerten Tickets:

- Bereichsauswahl (Ticket 04) und Aufnahme (Ticket 01) hinter ihrer
  Schnittstelle.
- Decode-Schleife in der Architektur aus Ticket 03 (Threads/Pool, Dedup,
  Grid, Stream-Neustart-Erkennung).
- Fenster nach Ticket 06: Seitenleiste (Fangrate, px/Modul, K, blockLen, Grid,
  Kompression, Dateiname, Restzeit), **Live-Vorschau** des Bereichs als Kachel,
  Fortschrittsbalken über **gesammelte Frames**, Empfehlungszeile nur unter der
  Fangraten-Schwelle, Speicherdialog am Ende, Schnipselanzeige, Verwerfen bei
  SHA-256-Fehlschlag.
- Bildschirm-Schlafsperre während des Empfangs (`caffeinate -w`, wie beim
  Sender).
- Von `python-sender` übernehmen statt neu erfinden: die UI-Bausteine, die
  Farbwelt, das Icon, die `caffeinate`- und Spawn-Behandlung.

Erledigt, wenn ein lokaler `decimen-send` neben dem Empfänger pixelgenau
empfangen wird **und** ein `decimen-send` durch eine echte Citrix-Sitzung
hindurch — SHA-256-verifiziert. Der pixelgenaue Fall beweist die Mechanik, der
Citrix-Fall das eigentliche Ziel.

## Stand — gebaut, wartet auf einen echten Strom

Wie beim Sender endet das Abnahmekriterium an etwas, das kein Test liefert: ein
lokaler `decimen-send` pixelgenau **und** ein `decimen-send` durch echtes
Citrix. Bis dahin bleibt das Ticket beansprucht.

### Was liegt

```
python-receiver/decimen/
  engine.py            ReceiverEngine — der Aufnahme-/Decode-Thread
  app.py               das Fenster: Seitenleiste + Live-Vorschau
  send_settings_hint.py  die Empfehlung aus der gemessenen px/Modul
  platform_bits.py     Icon, caffeinate, Speicherdialog (mit dem Sender geteilt)
  protocol.py fountain.py frame_capacity.py   die Decode-Hälfte (Ticket 05)
  capture.py select_region.py                 Aufnahme + Auswahl (Tickets 01, 04)
  ui.py                aus python-sender übernommen
  icon.png             dieselbe Marke in LIVE-Grün statt ACCENT-Blau,
                       damit Sender und Empfänger im Dock auseinandergehen
                       (`assets/make-icon.py`)
tests/
  test_conformance.py  167 Prüfungen (Ticket 05)
  test_engine.py       8 Prüfungen — die Thread-Architektur über eine FakeRegion
  test_app.py          9 Prüfungen — Speicherangebot und Panel-Zahlen, ohne Fenster
  smoke_window.py      das ganze Fenster über eine FakeRegion
  ts_roundtrip.py      gegen den TypeScript-Encoder (Ticket 05)
```

### Wie es zusammengesetzt ist

- **Aufnahme-/Decode-Thread** (`engine.py`), Architektur aus „Decode-Architektur":
  greift die Region ab, `zxing` findet alle Codes im Bild, `parse_frame`,
  **Stream-Identität vor `add_frame`** (ein Frame aus fremdem Strom würde den
  Peel stumm zerstören), `LTDecoder` baut zusammen. Kein Pool. Der optionale
  Bildhash-Vorfilter ist da, Standard aus.
- **Fenster** (`app.py`) liest nur `snapshot()` und zeichnet — die Fangrate
  koppelt nicht an die UI-Rate. Fortschritt über **gesammelte Frames**
  (`frames_new − frames_redundant`), Live-Vorschau des Bereichs rechts,
  Empfehlung nur nach 4 s unter der Fangraten-Schwelle.
- **Bereichsauswahl** blendet das eigene Fenster aus (`iconify`), damit es
  nicht in der Aufnahme landet; neu wählbar mit Leertaste, der Decoder läuft
  weiter (`engine.set_region`).
- **Am Ende** Speicherdialog (`platform_bits.save_dialog`, `choose file name`),
  Schnipsel im Fenster, Schlafsperre aus. SHA-256 wird vor dem Anbieten
  geprüft; scheitert er, wird gemeldet statt angeboten.

### Gemessen

Engine-Test: Datei über 15 % Verlust empfangen, SHA-256 verifiziert, und der
**Stream-Neustart setzt den Decoder sauber zurück** (fünf Frames Strom A, dann
Strom B — B kommt sauber an, nicht gemischt). Fenster-Rauchtest: Panel und
Vorschau zeichnen ohne Absturz, Datei kommt verifiziert an, px/Modul und
Fangrate werden gemessen.

### Feldversuch — Runde 1

Der erste Lauf am echten Fenster. Ein Strom kam **vollständig und
SHA-256-verifiziert** an — der Speicherdialog öffnet sich erst nach
`sha256_ok`, sein Erscheinen ist also der Beleg. Der Lauf hat zwei Fehler
freigelegt, die kein Test im Ordner sehen konnte, weil beide am Fenster hängen:

1. **Abbrechen im Speicherdialog öffnete ihn endlos wieder.** Der Wächter in
   `_offer` hing an `saved_path`/`snippet`; bei Abbruch wird keins von beiden
   gesetzt, also lief der Dialog in jedem UI-Frame erneut auf. Er hängt jetzt
   am **Datei-Objekt** (`snap.file is self._offered`) — ein neuer Strom bringt
   ein neues Objekt und wird von selbst wieder angeboten. Damit ein
   versehentlicher Abbruch die Übertragung nicht wegwirft, bietet **S**
   dieselbe Datei erneut an; die Statuszeile sagt das.
2. **Kein Durchsatz im Panel.** `throughput` (`Fangrate × blockLen`, in kB/s)
   und `time left` sind ergänzt. Die Restzeit stand seit „Empfänger-Fenster"
   in der Spezifikation und fehlte im Bau — nachgetragen, nicht neu erfunden.
   Der Wert ist Wire-Payload: bei Kompression ist die geschriebene Datei
   größer.

Nebenbei: der Schnipseltext wurde dekodiert und dann verworfen (`self.snippet`
zeichnete nirgends) — steht jetzt in der Statuszeile.

Beides festgenagelt in `tests/test_app.py` (9 Prüfungen, ohne Fenster:
30 UI-Frames nach Abbruch = genau ein Dialog, S = ein zweiter, neue Datei = ein
dritter; Durchsatz und Restzeit inkl. Rate 0). Der Fenster-Rauchtest läuft
weiter durch (`SDL_VIDEODRIVER=dummy`).

**Lehre für die Karte:** Die Fehler saßen beide dort, wo kein Test hinreicht —
im Dialog und im Panel. Der Feldversuch ist nicht die Abnahme einer fertigen
Sache, er ist die letzte Fehlerquelle.

**Runde 1 war lokal, pixelgenau** (Nutzer). Damit ist die **erste Hälfte des
Abnahmekriteriums erbracht**: ein lokaler `decimen-send` neben dem Empfänger
kommt SHA-256-verifiziert an. Die Mechanik steht — Auswahl, Aufnahme, zxing,
Peel, Container, Prüfsumme, Dialog. Offen bleibt allein der Citrix-Lauf.

### Gemessen: wo die Durchsatzgrenze sitzt

Runde 1 lief mit **120 kB/s**, und die Frage war, ob das das Maximum ist.
`assets/throughput-ceiling.py` misst zxing auf Frames, die der Sender genauso
rendert — **ganzzahlige Modulskala, 1:1 geblittet, kein Resampling**
(`pool.py`: `scale = display_px // (cell × cols)`), Fenster wächst in die Höhe,
die das Grid braucht:

| bytes | codes | px/Modul | Fenster | Decodes/s | kB/s @60fps |
|---|---|---|---|---|---|
| 2953 | 1 | 6 | 1110×1110 | 237 | 176 |
| 2953 | 2 | 6 | 1110×2220 | 110 | 352 |
| 2953 | 4 | 3 | 1110×1110 | 115 | 703 |
| 1850 | 1 | 7 | 1071×1071 | 292 | 110 |
| 1000 | 1 | 10 | 1130×1130 | 319 | 59 |

**Der Decoder ist nie die Grenze** — 110 bis 319 Decodes je Sekunde gegen einen
Sender, der bei 60 fps deckelt. Die Kette bei einem Code, 2953 B: Sender
60 fps × 2931 B = 176 kB/s Wire, Grab 123/s (Ticket 01), Fountain ~1,15·k →
netto ~153 kB/s. Gemessene 120 sind ≈41 brauchbare Frames von 60: die Lücke
sind Frames, die der ungetaktete Grab im Übergang oder doppelt erwischt, nicht
Rechenzeit. **Bildschirmgebunden, nicht rechengebunden.**

**Die Geometrie hat eine Kante, die die Karte so nicht hatte.** `grid_dims`
baut „höher vor breiter": 1→2 Codes fügt eine **Zeile** an, keine Spalte — die
Modulgröße bleibt unverändert, die Nutzlast verdoppelt sich, es kostet nur
Fensterhöhe. Erst 2→4 fügt eine Spalte an und halbiert px/Modul. Grids sind
also **nicht pauschal** Robustheitsrisiko: Zeilen sind in Modulgröße gratis,
Spalten nicht. (Über Citrix bleibt die doppelte Fläche trotzdem doppelt so
viel bewegtes Bild für HDX — gratis in px/Modul heißt nicht gratis in
Kompressionsqualität.)

### Ergänzt: der Empfänger sagt jetzt auch, wie es schneller geht

Die Empfehlung war einseitig — sie sprang nur bei schlechtem Empfang an.
`send_settings_hint.headroom()` ist die Gegenrichtung: bei gesundem Empfang und
Reserve über der Schwelle nennt sie die konkreten Sender-Schalter, die mehr
tragen, samt Faktor und verbleibender px/Modul. Beide Richtungen, eine Zahl.

- **Rechnet, statt zu raten.** Aus gemessener px/Modul, `blockLen` (also
  bytes/frame) und Code-Anzahl wird die Breite zurückgerechnet, die die Codes
  belegen, und jede Kombination aus `FRAME_BYTES_OPTIONS × GRID_OPTIONS`
  vorhergesagt. Das gilt auch über Citrix, weil die Breite aus der **Messung**
  kommt, nicht aus der Sender-Einstellung.
- **ECC kommt jetzt aus dem Code selbst.** zxing meldet `ec_level`. Vorher nahm
  der Empfänger stillschweigend L an — bei H braucht dieselbe Nutzlast ein weit
  größeres Symbol, px/Modul wurde also überschätzt, und zwar um mehr als der
  Abstand zur Schwelle beträgt, gegen die verglichen wird. Steht jetzt neben
  px/Modul im Panel.
- **Kapazitätstabelle exakt statt grob.** Die alte Interpolation in `engine.py`
  (`_CAP_L`, 9 Stützstellen) lag bei 500 B um vier Versionen daneben. Ersetzt
  durch die vollen 40 Versionen × 4 Stufen, **gegen segno erzeugt**
  (`assets/qr-capacity.py`), nicht zitiert.
- **Aufwärts wird eine Sicherheitsmarge gehalten** (`UPGRADE_PX = 8`, nicht 6).
  Die 6 stammt aus einer H.264-Simulation, die „Citrix-Robustheit" selbst als
  über echtes HDX zu bestätigen markiert hat — ein Rat, der genau darauf
  landet, verwettet die Übertragung auf eine unbestätigte Kante. Die
  Rettungszeile benutzt weiter die blanke Schwelle.

`tests/test_app.py` deckt das mit ab (19 Prüfungen): die Zeilen-vor-Spalten-
Kante, das Schweigen wenn nichts besser ist, und dass bei H nie eine
Rahmengröße vorgeschlagen wird, die ein Code auf dieser Stufe gar nicht trägt.

### Abgenommen — beide Hälften

**Runde 1 lokal, pixelgenau** (siehe oben) und **Runde 2 durch eine echte
Citrix-Sitzung**, beide SHA-256-verifiziert. Damit ist das Abnahmekriterium
erfüllt und das Ticket geschlossen.

Der Citrix-Lauf lief über die **GUI mit den Standardwerten** — also
`--fps 60 --bytes 2953 --ecc L --codes 1 --size 900`. Die Geometrie dazu, aus
`send_settings_hint` gerechnet: 2953 B ⇒ QR-Version 40 ⇒ 177 Module, Zelle 185
mit Ruhezone, ganzzahlige Skala `900 // 185 = 4`. Also **4 px/Modul, bei einem
tatsächlichen Bild von 740 px** (der Sender lässt 160 px des Fensters
ungenutzt, weil die Skala ganzzahlig ist).

**Das ist der interessanteste Befund des ganzen Tickets.** „Citrix-Robustheit"
hatte ≥6 px/Modul als robust und ≤3 als gebrochen gemessen — gegen eine
H.264-Simulation, ausdrücklich mit dem Vorbehalt, dass echtes HDX das
bestätigen muss. Der reale Lauf landet mit 4 **genau in der ungetesteten Lücke
dazwischen**, und er ging durch. Kein Widerspruch zur Simulation, aber eine
echte Verengung: **4 px/Modul reichen über echtes HDX.**

**Nichts nachgezogen.** Eine einzelne gelungene Übertragung ist kein Grund,
eine Sicherheitsmarge zu senken — was fehlt, ist ein Lauf, der *scheitert*,
denn erst der sagt, wo die Kante wirklich liegt. `TARGET_PX = 6` und
`UPGRADE_PX = 8` bleiben, wie sie sind.

Bemerkenswert ist dabei, dass die Gestaltung diesen Fall schon richtig
behandelt hat, ohne es zu wissen: die Rettungszeile hängt an der **Fangrate**,
nicht an px/Modul, und ist bei einem gesunden Strom mit 4 px/Modul stumm
geblieben — hätte sie an px/Modul gehangen, hätte sie eine funktionierende
Übertragung angemahnt.

Ungeprüft geblieben, weil der Lauf ohne Not durchging: Bereich mit Leertaste
nachziehen und Sender-Neustart, beide über Citrix. Sie stehen im Engine-Test
und im lokalen Lauf, nicht am echten Bild.

Startbefehl ist `uv run decimen-receive`; README und Repo-Verweise kommen aus
der Verpackung, die damit frei wird.
