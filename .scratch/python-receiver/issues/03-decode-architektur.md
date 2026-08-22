# Decode-Architektur: Aufnahme, Dedup, Grid, Fountain zusammenfügen

Type: grilling
Status: open
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
