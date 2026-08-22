# Aufnahme-Backends für Windows und Linux

Type: research
Status: resolved
Blocked by: —

## Question

Aus dem Nebel gehoben, weil die Bedingung erfüllt ist, die ihn dort hielt: die
macOS-Aufnahme **steht hinter ihrer Schnittstelle**. `capture.ScreenRegion`
nimmt einen Bereich in Punkten und liefert ein RGB-numpy-Array; `engine.py`
kennt nichts darunter. Damit ist die Frage stellbar, ohne Decode, Fenster oder
Fountain anzufassen.

Der Nutzer hat Unabhängigkeit ausdrücklich gewollt („unabhängig wäre gut"), sie
steht als Struktur in den Notizen der Karte — aber kein Backend existiert.

Zu klären:

- **Windows:** welche API liefert einen Bildschirmbereich schnell genug
  (>60 Aufnahmen/s bei ~1200 px), ohne Fensteraufzählung? Windows Graphics
  Capture, `BitBlt`/GDI, Desktop Duplication — was ist von Python aus ohne
  schwere Abhängigkeit erreichbar, und was kostet die Berechtigung?
- **Linux:** X11 vs. Wayland. Unter Wayland ist Bildschirmaufnahme
  portalgebunden — geht das ohne Nutzerdialog je Aufnahme?
- **Logische vs. physische Pixel.** Der Grund, aus dem `mss` auf macOS
  ausgeschieden ist (Ticket „Bildschirmbereich abgreifen"): es lieferte nur
  logische Punkte, und px/Modul hängt an physischen. Gilt derselbe Fallstrick
  auf Windows-Skalierung und Wayland-`scale`?
- **Passt die Schnittstelle?** Falls ein Backend nur einen Strom statt
  Einzelaufnahmen liefert, muss `ScreenRegion.grab()` sich ändern — das wäre
  die einzige Stelle, die die Portabilität wirklich kostet.

Erledigt, wenn je Plattform ein Backend benannt ist, mit Abhängigkeit,
erwarteter Rate und der Antwort, ob `ScreenRegion` unverändert bleibt.
Implementierung ist nicht Teil dieses Tickets — die Entscheidung ist es.

## Answer — Windows und X11 passen, Wayland ist eine andere Form

Je Plattform ein Backend, mit dem, was die Schnittstelle davon merkt.

### Windows: `dxcam` (Desktop Duplication)

Pull-basiert und rechteckförmig — genau die Form von `ScreenRegion`.
`camera.grab(region=(links, oben, rechts, unten))` liefert ein numpy-Array.
Das Projekt misst **239 fps** gegen 76 fps für `mss` und 118 für D3DShot; Wheels
für CPython 3.10–3.14, also gepflegt. Weit über dem Bedarf, wie auf macOS.

Drei Details, die der Adapter kennen muss:

1. **`grab()` gibt `None` zurück, wenn seit dem letzten Aufruf kein *neues*
   Bild kam** — Desktop Duplication liefert nur bei Änderung. Bei uns heißt
   `None` „Aufnahme fehlgeschlagen" (`_loop` schläft dann 50 ms). Das ist die
   einzige echte Kollision, und sie ist ein Schlüsselwort:
   **`new_frame_only=False`** liefert immer das aktuellste Bild.
2. **Rechteck-Konvention** ist `(links, oben, rechts, unten)`, unsere ist
   `(x, y, w, h)`. Trivial.
3. **BGRA nehmen, nicht `"RGB"`.** Die RGB-Ausgabe von dxcam braucht OpenCV;
   BGRA braucht nichts, und die Kanalscheibe dafür steht schon in `grab()`.

`windows-capture` (Windows Graphics Capture) ist die *unterstützte* moderne
API und leistungsmäßig vergleichbar, aber callback-/stromgetrieben. Dieselbe
Abwägung wie auf macOS zwischen Quartz und ScreenCaptureKit — die einfachere,
ältere API gewinnt heute, die moderne bleibt Aufstiegspfad.

### Linux: zwei Backends, nicht eins

- **X11: `mss`.** Unter X11 darf jeder Client die Pixel jedes anderen lesen —
  deshalb „funktionierte Screensharing dort einfach". Pull, Rechteck, kein
  Dialog. Der Grund, aus dem `mss` auf macOS ausschied (logische statt
  physischer Punkte), greift hier nicht: X11 virtualisiert nicht so.
- **Wayland: `xdg-desktop-portal` + PipeWire.** Das Sicherheitsmodell verbietet
  genau das, was X11 erlaubte. Aufnahme läuft über einen D-Bus-Portalaufruf,
  der Nutzer wählt in einem **Systemdialog** eine Quelle, und die Inhalte
  kommen als **PipeWire-Videostrom**.

### Bleibt `ScreenRegion` unverändert?

**Windows und X11: ja**, unverändert — beide sind Pull plus Rechteck.

**Wayland: die Klasse ja, die Bedienung nein.** Der Strom ist Push und die
Quelle ist ein *Bildschirm oder Fenster*, das der Nutzer im Portal wählt —
kein Rechteck, das wir benennen. Ein Backend kann `grab()` trotzdem erfüllen,
indem es das jeweils neueste Strombild hält und unser Rechteck herausschneidet.
Was sich ändert, ist die **Bereichsauswahl** aus ihrem Ticket: erst der
Portaldialog, dann das Aufziehen darin. Das ist die einzige Stelle, an der
Portabilität wirklich etwas kostet — und sie liegt nicht in `capture.py`.

### Logische vs. physische Pixel, je Plattform

Der Fallstrick aus „Bildschirmbereich abgreifen" wiederholt sich anders:

- **Windows:** Desktop Duplication liefert den echten Framebuffer, also
  physische Pixel. Aber der Prozess muss DPI-bewusst sein, damit die
  *Koordinaten* zu dem passen, was der Nutzer aufgezogen hat — sonst
  virtualisiert Windows sie. **Am Gerät zu prüfen, nicht zu glauben.**
- **Wayland:** fraktionale Skalierung — der Portalpuffer kann in einem anderen
  Maßstab liegen als das logische Layout.
- **X11:** in der Regel 1:1.

### Was daraus folgt

**Jetzt nichts bauen.** macOS steht, kein Nutzer wartet auf Windows oder Linux.
Wenn es soweit ist: Windows sind rund 40 Zeilen (dxcam), X11 rund 30 (mss),
und Wayland ist ein eigenes Vorhaben, weil es die Auswahl anfasst und nicht
nur die Aufnahme — dann als eigenes Ticket, mit der Portal-Frage als Kern.
Die Erkenntnis steht als Absatz in `capture.py`, wo ein späterer Implementierer
zuerst hinsieht.

Quellen: [DXcam](https://github.com/ra1nty/DXcam),
[DXcam README](https://github.com/ra1nty/DXcam/blob/main/README.md),
[dxcam auf PyPI](https://pypi.org/project/dxcam/),
[Wayland vs X11 2026](https://glukhov.org/post/2026/01/wayland-vs-x11-comparison),
[libscreencapture-wayland](https://github.com/DafabHoid/libscreencapture-wayland).
