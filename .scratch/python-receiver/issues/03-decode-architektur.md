# Decode-Architektur: Aufnahme, Dedup, Grid, Fountain zusammenfügen

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

Wie fügen sich Aufnahme, QR-Dekodierung und Fountain-Decoder zu einer
Schleife, die mit der Aufnahmerate mithält?

Die Bausteine und ihre Spannungen:

- **Aufnahme läuft schneller als neue Frames erscheinen.** Der Sender zeigt
  jeden Frame mehrere Aufnahme-Bilder lang; derselbe QR-Code wird also
  mehrfach gelesen. Deduplizierung über die `seq` im Header ist Pflicht,
  sonst dekodiert der Empfänger denselben Frame zwanzigmal. Der `LTDecoder`
  hat dafür bereits ein `seen`-Set — reicht das, oder muss schon vor dem
  teuren QR-Decode dedupliziert werden (Bildhash)?
- **Grids.** Ein Bild enthält 1, 2, 4 oder 6 Codes. `zxing-cpp` kann mehrere
  pro Bild finden, das kostet Suchzeit. Muss die Grid-Anzahl erkannt werden,
  oder sucht man einfach immer „alle Codes im Bild"?
- **QR-Decode ist teuer.** Beim Sender war Kodieren der Engpass und ein
  Prozess-Pool die Antwort. Ist Dekodieren hier der Engpass, und lohnt
  derselbe Pool — oder hält ein Thread mit, weil viele Aufnahme-Bilder
  ohnehin denselben (schon gesehenen) Frame tragen?
- **Aufnahme blockiert die UI nicht.** Läuft die Aufnahme in einem eigenen
  Thread und die pygame-Schleife zeigt nur Fortschritt, oder pumpt eine
  Schleife beides?
- **Stream-Neustart.** Erkennt der Empfänger über die Stream-Identität, dass
  der Sender neu gestartet hat (neue `sessionId`), und setzt zurück?

Zu entscheiden ist die Grobarchitektur — Threads, Pool ja/nein,
Dedup-Ebene, Grid-Strategie —, gestützt auf die Zahlen aus „Bildschirmbereich
abgreifen" (Aufnahmerate) und „Citrix-Robustheit" (wie viele Frames real
brauchbar ankommen). Räumt den Nebel-Eintrag zum Stream-Neustart ab.

## Answer

**Ein Hintergrund-Thread greift ab und dekodiert, die pygame-Schleife zeigt
nur an. Kein Prozess-Pool.** Die Messung hat das entschieden, nicht der
Geschmack.

### Was die Messung ergab

QR-Decode je Aufnahme-Bild, einthreadig:

| Aufbau | Decode | Bildhash | Verhältnis |
|---|---|---|---|
| 1 Code v40 | 2,68 ms | 0,010 ms | 273× |
| 1 Code v22 | 0,61 ms | 0,004 ms | 153× |
| 4er-Grid v22 | 6,83 ms | 0,014 ms | 491× |
| 6er-Grid v24 | 7,75 ms | 0,024 ms | 322× |

Der schlimmste Fall (6er-Grid) sind **129 Decodes/s auf einem Thread** — weit
über jeder realen Citrix-Frame-Rate. **Anders als beim Sender ist Dekodieren
nicht der Engpass**, weil die reale Rate über Citrix niedrig ist. Der
Prozess-Pool, der beim Sender nötig war, entfällt hier ersatzlos.

### Die Architektur

- **Ein Aufnahme-/Decode-Thread**, unabhängig von der UI-Bildrate (Q1a). Sonst
  koppelt die Fangrate an die Zeichenrate, und ein träge zeichnendes Fenster
  verschluckt Frames. Der Thread greift so schnell ab, wie der Decode erlaubt
  (>2× die maximale Sender-fps von 60, also sicher jeder Frame), dedupliziert
  und speist den `LTDecoder`.
- **Die pygame-Schleife zeigt nur an.** Sie liest einen thread-sicher
  übergebenen Zustand (Fortschritt, Fangrate, Parameter) und zeichnet. Der
  Thread wird beim Beenden sauber gestoppt, wie `caffeinate` beim Sender.
- **Dedup über `seq`**, im `LTDecoder` bereits vorhanden (`seen`-Set,
  `shared/fountain.ts:250`). Reicht: der Decode ist billig genug, dass
  Mehrfach-Lesen desselben Frames folgenlos ist.
- **Bildhash-Vorfilter als Option, Standard aus** (Q2). Er spart im
  **pixelgenauen** Fall >90 % der Decodes (identische Bilder), ist über Citrix
  aber wertlos, weil Kompressionsrauschen jedes Bild verändert — ein exakter
  Hash trifft nie. Standard aus, weil Citrix das Ziel ist; ein Schalter für
  den Entwicklungsfall am lokalen Sender.
- **Grids: immer „alle Codes im Bild suchen".** `zxing-cpp` findet mehrere
  Codes pro Bild ohnehin; die Grid-Anzahl muss nicht erkannt werden. Jeder
  gefundene Code ist ein gewöhnlicher Frame — der Fountain braucht keine
  Vorstellung von „Layout", genau wie beim Sender.
- **Stream-Neustart über die Stream-Identität.** Der erste geparste Frame
  liefert `sessionId`/`k`/`blockLen`/`totalLen`. Ändert sie sich — der Sender
  hat neu gestartet und eine neue `sessionId` gezogen —, wird ein frischer
  `LTDecoder` gebaut und der alte verworfen. Das räumt den gleichnamigen
  Nebel-Eintrag der Karte ab.

### Was zerfällt, wenn man es falsch macht

Der `LTDecoder` wird mit **festen** `k`/`blockLen`/`sessionId`/`totalLen`
konstruiert. Ein Frame aus einem anderen Stream (falsche Identität) darf ihm
nie übergeben werden — sonst mischt er zwei Dateien. Die Identitätsprüfung
sitzt also **vor** `addFrame`, nicht darin.
