# Fenster-Toolkit: welche Bildrate hält es auf macOS

Type: prototype
Status: resolved

## Question

Womit wird das Fenster gebaut — und welche Bildrate hält es beim Blitten von
QR-Frames durch?

Kandidaten:

- **tkinter** — Standardbibliothek, also null zusätzliche Abhängigkeit und
  perfekt zum „Ordner kopieren"-Ziel passend. Ruf auf macOS eher schlecht;
  `PhotoImage` gilt bei größeren Bildern als langsam.
- **pygame-ce** — SDL darunter, 60 fps sind dort Routine, kostet ein Wheel.
  Über `uv sync` (Karte: entschieden) kein Problem.

Gemessen wird das, was das Programm wirklich tut: ein bereits gerastertes
RGB-Bild in QR-Größe (grob 600×600 bis 1400×1400, je nach Grid) pro Frame
auf den Bildschirm bringen, in einer Schleife mit fester Zielrate, über
mindestens 30 Sekunden — mit der tatsächlich erreichten Rate als Ergebnis,
nicht der angeforderten.

**Zielmarke steht inzwischen fest.** Der QR-Encoder liefert bei 2953 Bytes
60 Kodierungen/s (Ticket 01). Die Anzeige muss also 60 fps bei einem
einzelnen Code oder 15 fps bei einem 4er-Grid halten — nicht mehr. Bleibt
ein Kandidat darunter, ist er raus; liegt er deutlich darüber, ist die
Anzeige nicht der Engpass und die Wahl fällt auf die geringere
Abhängigkeit.

Wichtig: dieses Ticket misst **nur die Anzeige**. Die Kodierung misst Ticket
01. Erst beide Zahlen zusammen ergeben die erreichbare Bildrate.

Die Antwort nennt das gewählte Toolkit, die gehaltene Bildrate je Kandidat,
und ob die Plattform-Annahme der Karte (macOS) dabei ins Gewicht fiel.

## Answer

**pygame-ce für das Stream-Fenster, tkinter für die Bedienung — beide im
selben Prozess.**

### Bildrate, gemessen

Jeder Frame ist ein neues Bild aus rohen Bytes, kein Cache, 20 Sekunden je
Fall:

| Toolkit | 740×740 px (1 Code @4×) | 1480×1480 px (4er-Grid @4×) |
|---|---|---|
| tkinter (Tk 9.0) | 52,6 fps | 23,4 fps |
| pygame-ce 2.5.8 | 120,0 fps (vsync-gedeckelt) | 315,8 fps |

Die 120,0 sind exakt die Bildwiederholrate des Schirms — nicht pygames
Grenze. Beim 1480er Fenster greift der Deckel nicht, dort zeigt sich die
rohe Fähigkeit von über 300 fps.

**tkinter verfehlt die Zielmarke beim Einzelcode** (52,6 < 60 fps) — und
zwar ohne dass der Encoder gleichzeitig um CPU konkurriert.

### Die ganze Kette, gemessen

Wichtiger als beide Einzelwerte: kodieren, rastern und anzeigen in einer
Schleife, wie der Sender es wirklich tut.

| Aufbau | Bildrate | Nutzdurchsatz | kodieren | rastern | anzeigen |
|---|---|---|---|---|---|
| 1 Code @740px | 60,7 fps | **151,1 KB/s** | 92,5 % | 6,2 % | 1,3 % |
| 4er-Grid @1480px | 15,2 fps | **151,3 KB/s** | 92,2 % | 6,1 % | 1,7 % |

Das bestätigt die Vorhersage aus „QR-Encoder in Python" auf zwei
Nachkommastellen genau: ~151 KB/s, unabhängig vom Aufbau. **Mit pygame ist
die Anzeige mit 1,3–1,7 % der Zeit schlicht kein Faktor mehr.**

Mit tkinter wäre sie einer. Gegenrechnung aus den gemessenen Werten: beim
Einzelcode kostet die Anzeige 19,0 ms statt 0,2 ms, der Frame damit 35,3
statt 16,5 ms → **28 fps und 70 KB/s**. Beim 4er-Grid 9,3 fps und 93 KB/s.
tkinter kostet also **40 bis 55 % des Durchsatzes** — für eine gesparte
Abhängigkeit, die durch die Entscheidung „`uv sync` ist in Ordnung" (Q9)
ohnehin nichts mehr wert ist.

### Warum trotzdem tkinter dabeibleibt

pygame hat **keine Bedienelemente**. Kein Schieberegler, kein Knopf, kein
Dateidialog — alles müsste von Hand gezeichnet werden. tkinter hat sie,
inklusive nativem `filedialog`.

Geprüft, dass beides zusammengeht: Tk-Fenster mit Schieberegler aufmachen,
danach im selben Prozess ein pygame-Fenster, und beide Ereignisschleifen in
einem Durchlauf pumpen — **läuft, 402 Durchläufe/s**. Auf macOS war das die
offene Frage, weil Cocoa Fensterarbeit auf dem Hauptthread verlangt; die
Antwort ist, dass `root.update()` und `pygame.event.pump()` sich in
derselben Schleife vertragen.

Damit fällt die Arbeitsteilung natürlich aus: **tkinter dort, wo Widgets
zählen, SDL dort, wo die Bildrate zählt.** Das nimmt der Frage nach ein oder
zwei Fenstern (Ticket „Fensteraufteilung") die technische Hälfte ab — zwei
Fenster sind ohnehin die Bauform.

Zugabe: Drag & Drop ist bei pygame umsonst dabei (`pygame.DROPFILE`, geprüft
vorhanden). Bei tkinter bräuchte es `tkinterdnd2`, eine Tcl-Erweiterung.

### Falle für die Verpackung

**Homebrews `python@3.13` bringt kein tkinter mit** — Homebrew trennt es in
ein eigenes Formel-Paket (`python-tk@3.13`) ab, das hier für 3.13 nicht
installiert ist. Ein venv auf dieser Basis stirbt an
`ModuleNotFoundError: No module named '_tkinter'`.

Das von **uv selbst verwaltete Python bringt tkinter mit, Tk 9.0** — geprüft
mit `uv venv --python-preference only-managed`. Das ist auch der Fall, der
auf einer fremden Maschine eintritt.

Für „Verpackung: uv, Startbefehl, CLI, README" heißt das: **die
Python-Wahl muss auf das verwaltete Python festgelegt werden**, sonst
greift uv auf einer Entwicklermaschine ein vorhandenes Homebrew-Python ab
und das Programm startet nicht. Der Startbefehl muss das erzwingen, nicht
hoffen.

### Abhängigkeiten, Stand jetzt

`segno` (QR), `pygame-ce` (Stream-Fenster), `pillow` (Rasterung, 6 % der
Zeit, in C). tkinter kommt aus der Standardbibliothek — sofern das richtige
Python gewählt ist.

### Assets

- `.scratch/python-sender/assets/display-bench.py` — Bildratenmessung je
  Toolkit.
- `.scratch/python-sender/assets/pipeline-bench.py` — die ganze Kette mit
  Zeitanteilen; die Vorlage für jede spätere Durchsatzmessung.
