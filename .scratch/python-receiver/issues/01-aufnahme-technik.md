# Bildschirmbereich abgreifen: welche Technik, wie schnell?

Type: prototype
Status: resolved

## Question

Womit wird ein rechteckiger Bildschirmbereich abgegriffen — und wie viele
Bilder pro Sekunde schafft das, bei welcher Latenz?

Das ist die Grundlage: ohne einen schnellen, verlässlichen Weg von „Bereich"
zu „RGB-Bild" gibt es nichts zu dekodieren. Die Aufnahme muss mindestens so
schnell sein wie die Bildrate des Senders (bis 60 fps), damit kein sichtbarer
Frame ungesehen vorbeizieht — bei Citrix ist die effektive Rate niedriger,
aber die Messung soll den pixelgenauen Best Case kennen.

Kandidaten auf macOS:

- **`mss`** (reines Python über CoreGraphics, plattformübergreifend, MIT).
  Einfachster Weg, ein Backend für alle Systeme. Ruf: eher langsam, kopiert
  viel. Zu messen, nicht zu glauben.
- **Quartz `CGDisplayCreateImageForRect` / `CGWindowListCreateImage`** über
  pyobjc. Region-Capture direkt, aber seit macOS 14 als veraltet markiert —
  läuft noch, kann aber in einer künftigen macOS-Version wegfallen.
- **ScreenCaptureKit** — der von Apple unterstützte Weg ab macOS 14, auf
  einen Bereich zuschneidbar, für hohe Bildraten gebaut. Offene Frage: die
  Python-Anbindung. `pyobjc-framework-ScreenCaptureKit` ist zu prüfen; das
  API ist rückruf- und async-lastig, was in einer pygame-Schleife Struktur
  kostet.

Gemessen wird eine ~740×740-Region über mindestens 20 Sekunden: erreichte
Bildrate, Latenz je Bild, und ob das Ergebnis auf einem Retina-Schirm die
physischen Pixel liefert oder die logischen Punkte (2× skaliert — wichtig,
weil ein QR-Modul dann doppelt so viele Pixel hat).

**Berechtigung nötig** — der Nutzer erteilt sie dem Terminal. Ohne sie liefert
Einzelaufnahme `kein Bild` (gemessen).

Die Antwort nennt das gewählte Backend, die Bildrate je Kandidat, und legt die
schmale Schnittstelle fest (Bereich → RGB-Bild), hinter der später ein
Windows-/Linux-Backend sitzen kann.

## Answer

**Quartz `CGWindowListCreateImage`, physische Pixel, hinter der Schnittstelle
`ScreenRegion` (Bereich in Punkten → RGB-numpy-Array).**

Berechtigung ist inzwischen erteilt (Region-Capture liefert echte Pixel).

### Gemessen

Eine 740-Punkte-Region, 6 s je Kandidat:

| Backend | Bildrate | Latenz median | Ausgabe |
|---|---|---|---|
| mss | 166 fps | 5,5 ms | **740×740 — nur logische Punkte** |
| Quartz `CGWindowListCreateImage` | 123 fps | 7,9 ms | 1480×1480 physisch |
| Quartz `CGDisplayCreateImageForRect` | 283 fps | 2,3 ms | 1480×1480 physisch |

**mss scheidet aus**, obwohl es in fps führt: es liefert logische Punkte, ein
QR-Modul hätte damit halb so viele Pixel — genau das Gegenteil dessen, was
Dekodierung gegen Kompression braucht.

**`CGDisplayCreateImageForRect` ist am schnellsten, aber am stärksten
gefährdet:** auf macOS 15+ wurde diese Funktion entfernt. `CGWindowListImage`
ist ebenfalls veraltet (seit macOS 14), läuft aber auf 26.5.2 und ist der
konservativere der beiden. Bei 123 fps liegt sie weit über der Decke von 60 fps,
die ein Sender überhaupt erzeugt — und über Citrix ist die reale Rate
niedriger. Der schnellere Weg kauft also nichts, was gebraucht wird.

Deshalb `CGWindowListCreateImage`. **ScreenCaptureKit** ist über
`pyobjc-framework-ScreenCaptureKit` verfügbar (inkl. `SCScreenshotManager`, dem
Einzelbild-Weg ab macOS 14) und ist der Upgrade-Pfad, falls eine künftige
macOS-Version die alte API wirklich entfernt. Es jetzt zu bauen kostet einen
async Completion-Handler und CMSampleBuffer-Entpacken für Durchsatz, der schon
gedeckt ist — nicht heute.

### Ende-zu-Ende belegt, nicht nur die Aufnahme

Ein echter Sender-Frame in ein Fenster gemalt, genau seine Region abgegriffen,
mit `zxing-cpp` dekodiert: **die Bytes stimmen mit der Quelle überein.** Und die
ganze Kette — grab + BGRA→RGB-Konversion + Decode — **hält 62/s** bei einem
einzelnen Code auf 1330×1330. Das ist der pixelgenaue Best Case; wie viel davon
über Citrix übrig bleibt, misst „Citrix-Robustheit".

### Die Schnittstelle

`.scratch/python-receiver/assets/capture.py` — `ScreenRegion(x, y, w, h)` mit
einem `grab()`, das ein `(H, W, 3)`-uint8-RGB-Array physischer Pixel liefert
oder `None`, wenn die Aufnahme scheiterte (fehlende Berechtigung → schwarzes
Bild ohne Fehler, muss der Aufrufer als „nichts empfangen" behandeln).

Zwei Fakten, die das Backend prägen und die jedes Ersatz-Backend einhalten
muss:

- **Bereich in Punkten, Bild in physischen Pixeln.** 740 Punkte → 1480 Pixel
  auf einem 2×-Schirm. Die Bereichsauswahl (Ticket „Bereichsauswahl") muss
  Punkte liefern, und der Skalierungsfaktor darf die Koordinaten nicht
  verschieben.
- **Zeilen-Padding.** `CGImageGetBytesPerRow` kann größer als `Breite × 4`
  sein; die numpy-Konversion schneidet es weg. Naiv `raw` als `w×h×4` zu
  lesen liefert sonst Schräglauf.

Die Konversion ist reines numpy-Slicing (`bgra[:, :, [2,1,0]]`), kein
Python-Pixel-Loop — der erste Versuch mit einer Doppelschleife war für 60 fps
unbrauchbar.

### Assets

- `.scratch/python-receiver/assets/capture.py` — die `ScreenRegion`-Schnittstelle
  und das macOS-Backend. Vorlage für „Den Empfänger bauen".

Laufzeitabhängigkeiten, die das festlegt: `pyobjc-framework-Quartz`, `numpy`,
`zxing-cpp`. `pyobjc-framework-ScreenCaptureKit` nur, wenn der Upgrade-Pfad
gegangen wird.
