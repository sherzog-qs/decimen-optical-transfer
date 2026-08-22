# Wie viel Citrix-Kompression überlebt ein QR-Code?

Type: prototype
Status: resolved

## Question

Citrix liefert keinen pixelgenauen Strom (siehe Karte). Bevor der Empfänger
gebaut wird, muss klar sein, **bei welchen Sender-Einstellungen** ein Code die
Kompression überhaupt noch übersteht — denn genau darauf zielen die
Empfehlungen des Empfängers.

Ohne echtes Citrix messbar durch Simulation: ein gerasterter QR-Frame (aus
`python-sender`s `qr.py`) wird durch einen H.264-Encode/Decode-Zyklus gejagt
(`ffmpeg`, verschiedene CRF-/Bitraten-Stufen, Chroma-Unterabtastung 4:2:0),
optional skaliert, und dann mit `zxing-cpp` dekodiert. Gemessen wird die
Dekodier-Erfolgsrate über:

- **QR-Version** — kleine Frame-Bytes ergeben niedrige Versionen mit fetten
  Modulen (Version 15 bei 500 Bytes hat ~5× die Modulfläche von Version 40 bei
  2953). Die Vermutung: fette Module überleben Blockartefakte weit besser.
- **Kompressionsstärke** — CRF 23 bis CRF 40, plus ein Bitraten-gedeckelter
  Fall, der Citrix' aggressiven Modus nachstellt.
- **Skalierung** — 1:1 gegen auf krumme Größen interpoliert.
- **ECC-Stufe** — L gegen H, gegen dieselbe Nutzlast.

Wichtige Einschränkung, die in die Antwort gehört: **H.264 aus ffmpeg ist
nicht Citrix HDX.** Die Simulation zeigt die *Richtung* (fette Module gut,
hohe Versionen schlecht) verlässlich, aber die konkreten Schwellen sind
Näherungen. Der echte Beleg ist ein Messlauf über eine echte Citrix-Sitzung,
und der ist Teil der Abnahme, nicht dieses Tickets.

Die Antwort nennt die Sender-Einstellungen, die die Simulation überstehen,
als Ausgangspunkt für die Empfehlungslogik — und hält fest, dass sie über
echtes Citrix zu bestätigen sind.

## Answer

**Die Modul-Pixelgröße entscheidet — nichts anderes kommt in ihre Nähe.**
Ziel für Robustheit: **≥6 px je QR-Modul** in der Aufnahme, ≥8 px für harte
Sitzungen. Darunter wird es zur Kippzone, ≤3 px bricht.

### Gemessen

Echte, wechselnde Sender-Frames (kein Standbild — Citrix' Nachschärfen greift
nur bei Bewegung) durch libx264 und zurück, Frame für Frame dekodiert. Bei
fester 740-px-Aufnahmefläche, unter harten Bedingungen (starke Kompression +
Verkleinerung der Sitzung):

| Bytes/Frame | ECC | Grid | Version | px/Modul | CRF38 | CRF42 +0,6× | CRF46 +0,5× |
|---|---|---|---|---|---|---|---|
| 500 | L | 1 | v15 | 8 | 100 % | 100 % | 100 % |
| 1000 | L | 1 | v22 | 6 | 100 % | 100 % | 41 % |
| 1465 | L | 1 | v27 | 5 | 100 % | 97 % | 0 % |
| 2953 | L | 1 | v40 | 4 | 100 % | 0 % | 0 % |
| 1000 | H | 1 | v36 | 4 | 100 % | 84 % | 0 % |
| 500 | L | 4 | v15 | 4 | 100 % | 2 % | 0 % |
| 1000 | L | 4 | v22 | 3 | 100 % | 0 % | 0 % |
| 500 | H | 6 | v24 | 3 | 100 % | 0 % | 0 % |

### Was das für die Empfehlung heißt

Der Empfänger kann die Modul-px selbst ausrechnen: **`px/Modul =
Aufnahmebreite / (Grid-Spalten × (QR-Version-Module + Ruhezone))`**. Die
QR-Version steht nicht im Frame-Header — aber die Zahl der Module ergibt sich
aus der Kantenlänge des dekodierten Codes, die zxing liefert. Daraus die
Empfehlung:

1. **Weniger Bytes je Frame ist der stärkste Hebel.** 500 statt 2953 senkt die
   Version von 40 auf 15 und verdoppelt die Modulfläche. Das schlägt alles
   andere.
2. **Grids sind über Citrix ein Risiko, kein Gewinn.** Ein 4er-Grid drittelt
   die Modul-px gegenüber einem Einzelcode. **Das kehrt die Sender-Logik um:**
   dort gab Grid Durchsatz, hier zerstört es Robustheit. Genau dieser
   Zielkonflikt gehört in die Empfehlung.
3. **ECC hilft nur im Grenzfall** (4 px: H hält, L fällt), kostet aber Version
   und damit Modul-px — zweitrangig gegenüber 1 und 2.

### Die Einschränkung, ausdrücklich

**H.264 aus ffmpeg ist nicht Citrix HDX.** Die konkreten CRF-Schwellen sind
Näherungen — reales HDX kann bei bewegten Regionen aggressiver sein oder Frames
verwerfen, was hier gar nicht modelliert ist. **Verlässlich ist die
Monotonie:** mehr Pixel je Modul überlebt mehr Kompression, immer. Die
Empfehlungslogik hängt an dieser Monotonie, nicht an den Absolutwerten — und
die absoluten Schwellen sind über eine echte Citrix-Sitzung zu bestätigen
(Teil der Abnahme, siehe „Den Empfänger bauen").

### Ein Testartefakt, das fast falsche Schlüsse erzwungen hätte

Der erste Lauf zeigte v22 bei **0 %** über alle CRF-Stufen, auch bei
fast verlustfreiem CRF18 — während v40 alles überstand. Unmöglich, wenn es
Kompression wäre (v22 hat fettere Module). Ursache: `yuv420p` verlangt gerade
Kantenlängen, und genau die 0 %-Fälle hatten ungerade Pixelbreiten (565, 645,
745, 845) — ffmpeg verschob das Bild. Die Bilder werden jetzt auf gerade Größe
weiß aufgefüllt. Ohne diese Prüfung wäre die Empfehlung „hohe Versionen
überleben nie" gewesen — das genaue Gegenteil der Wahrheit.

### Assets

- `.scratch/python-receiver/assets/citrix-compression-sim.py` — der
  CRF-Sweep über Bytes/ECC/Grid.
- `.scratch/python-receiver/assets/citrix-scale-grid-sim.py` — Skalierung,
  Grid-Zerfall und die harte Bruchkurve. Die Formel `px/Modul` und ihre
  Monotonie sind die Grundlage der Empfehlungslogik im Fenster-Ticket.
