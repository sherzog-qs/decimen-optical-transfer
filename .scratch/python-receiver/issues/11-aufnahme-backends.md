# Aufnahme-Backends für Windows und Linux

Type: research
Status: open
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
