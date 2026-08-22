# Bereichsauswahl: aufziehen wie Cmd-Shift-4

Type: prototype
Status: resolved
Blocked by: 01

## Question

Wie zieht man den Aufnahmebereich auf? Entschieden ist die Geste (Charting
Q7: aufziehen wie das macOS-Bildschirmfoto), offen ist die Umsetzung.

Nötig: ein abgedunkeltes, bildschirmfüllendes, klickdurchlässiges Overlay, auf
dem man ein Rechteck aufzieht; beim Loslassen steht der Bereich fest und das
Overlay verschwindet. Auf einem Mehrschirm-Aufbau muss es alle Schirme
abdecken.

Offene Punkte, die der Prototyp klärt:

- **Womit das Overlay?** pygame kann ein randloses Vollbildfenster, aber ein
  *klickdurchlässiges, halbtransparentes über allem* ist auf macOS nicht
  pygames Stärke. Alternative: ein natives `NSWindow` über pyobjc, oder — der
  einfachste Weg — gar kein eigenes Overlay, sondern das macOS-eigene
  `screencapture -i` aufrufen, das die Auswahlgeste fertig mitbringt und die
  Koordinaten liefert. Letzteres ist plattformgebunden, aber die
  Bereichsauswahl ist ohnehin hinter derselben Schnittstelle wie die Aufnahme
  (Ticket 01) portierbar.
- **Punkte, nicht Pixel** (festgelegt in „Bildschirmbereich abgreifen"). Die
  Aufnahme erwartet den Bereich in Bildschirm-**Punkten** und liefert physische
  Pixel zurück (2× auf Retina). Die Auswahl muss also Punkte liefern; ein
  Overlay, das in physischen Pixeln misst, verschiebt den Bereich um den
  Skalierungsfaktor.
- **Was der Bereich zurückgibt** — physische Pixel oder logische Punkte, und
  in welchem Koordinatensystem die Aufnahme aus Ticket 01 sie erwartet. Die
  beiden müssen sich einig sein, sonst greift man den falschen Fleck ab.
- **Nachjustieren.** Muss der Bereich während des Empfangs verschiebbar sein
  (das Citrix-Fenster wandert), oder reicht „neu aufziehen"?

Antwort: die gewählte Auswahlmethode, verlinkter Prototyp, und die
Koordinaten-Übergabe an die Aufnahme.

## Answer

**Aufziehen auf einem eingefrorenen Vollbild-Standbild, reines pygame. Bereich
in Punkten, während des Empfangs neu aufziehbar ohne Neustart.**

### Die Methode

Kein transparentes, klickdurchlässiges Overlay — das kann pygame auf macOS
schlecht. Stattdessen der Trick, den Cmd+Shift+4 optisch nachahmt: **ein
Vollbild-Standbild wird abgedunkelt gezeigt, der aufgezogene Bereich leuchtet
hell auf**, ein Rahmen zieht mit. Reines pygame, kein natives `NSWindow` und
kein `screencapture -i` — portiert also mit dem Aufnahme-Backend mit (Ticket
„Bildschirmbereich abgreifen"). `screencapture -i` wurde verworfen, weil es ein
Foto macht und keine Koordinaten liefert; wir brauchen die Region, um sie live
abzugreifen.

Prototyp: `.scratch/python-receiver/assets/select_region.py` (die Geste),
`try_select.py` (zum Ausprobieren — zieht auf, zeigt dann den gegriffenen
Ausschnitt).

### Die Koordinaten-Kette, verifiziert

pygame-Vollbild und der Bildschirm melden **beide 1800×1169 Punkte** — die
aufgezogenen Fensterkoordinaten sind also schon in den Punkten, die
`ScreenRegion` erwartet. **Keine Skalierungs-Umrechnung**, genau die Falle, die
Ticket „Bildschirmbereich abgreifen" benannt hat. Synthetisch geprüft: einen
Bereich „auswählen", greifen, dekodieren — die griffenen physischen Pixel sind
exakt 2× die gewählten Punkte, und die Bytes stimmen mit der Quelle überein.

### Die UX-Lehre, die der Test erzwungen hat

Ein **exakt** um den QR-Rand gezogener Bereich (340×340) dekodiert **nicht**;
mit 15 Punkten Rand drumherum schon. Grund: zxing braucht die weiße Ruhezone um
den Code, und pixelgenaues Rahmen schneidet sie an. Das ist eine gute Nachricht
— kein Mensch zieht mit der Maus pixelgenau, der reale Fall (grob drumherum) ist
genau der robuste. Empfehlung für den Bau: einen kleinen Sicherheitsrand
tolerieren oder automatisch addieren, damit knappe Auswahl nicht am Rand
scheitert.

### Nachjustieren ohne Neustart

Der Bereich ist **während des Empfangs neu aufziehbar** (eine Taste bringt das
Standbild zurück, neu ziehen). Der laufende `LTDecoder` bleibt und sammelt
weiter — er hängt nicht am Bereich, sondern an der Stream-Identität, also kostet
ein verrutschtes Citrix-Fenster keinen halb vollen Transfer. Über Citrix trifft
man den Bereich selten beim ersten Zug perfekt; das war der ausschlaggebende
Grund.

### Was der Bereich zurückgibt

`(x, y, w, h)` in Bildschirm-Punkten, oder `None` bei Abbruch (Esc) oder einer
zu kleinen Auswahl (<20×20, fängt einen Fehlklick ab). Geht direkt an
`ScreenRegion(x, y, w, h)`.

### Assets

- `.scratch/python-receiver/assets/select_region.py` — die Auswahl-Geste.
- `.scratch/python-receiver/assets/try_select.py` — der Ausprobier-Läufer.
