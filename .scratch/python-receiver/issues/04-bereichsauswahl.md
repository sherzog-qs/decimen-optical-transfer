# Bereichsauswahl: aufziehen wie Cmd-Shift-4

Type: prototype
Status: open
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
