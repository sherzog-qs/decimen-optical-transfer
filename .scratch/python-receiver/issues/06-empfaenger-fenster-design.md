# Empfänger-Fenster: Fortschritt, Statistik, Empfehlung, Speichern

Type: grilling
Status: resolved
Blocked by: 03

## Question

Was zeigt das Fenster während und nach dem Empfang?

Der Umfang steht (Charting Q5, Q7-neu, Q10), die Gestalt nicht:

- **Während des Empfangs:** Fortschritt (gelöste Blöcke von K), Fangrate
  (brauchbare Frames je Sekunde), geschätzte Restzeit, erkannte
  Stream-Parameter (K, blockLen, Grid-Anzahl, Dateiname sobald der Container
  ihn hergibt). Der Fortschritt ist die einzige Rückmeldung, ob es läuft —
  gegen Citrix blind, deshalb zentral.
- **Empfehlung.** Der Empfänger sieht als Einziger die Fangrate und die
  Modulgröße. „Citrix-Robustheit" hat die Grundlage geliefert: Robustheit hängt
  an **px/Modul = Aufnahmebreite / (Grid-Spalten × Modulzahl)**, Ziel ≥6.
  Daraus konkrete **Sender-Empfehlungen** in der Reihenfolge weniger Bytes/Frame
  → weniger Grid-Codes → höhere ECC — nie Citrix-Einstellungen (darauf hat der
  Nutzer kaum Einfluss). Zu entscheiden: wie viel davon automatisch aus der
  gemessenen Modulgröße abgeleitet wird und wie es formuliert ist.
- **Am Ende:** Datei über einen Speicherdialog ablegen (Charting Q10:
  gefragt, wohin), Textschnipsel im Fenster anzeigen zum Kopieren. SHA-256
  wird vor dem Anbieten verifiziert.
- **Der Bereich.** Zeigt das Fenster einen Live-Ausschnitt des aufgenommenen
  Bereichs (damit man sieht, dass man den richtigen Fleck trifft), oder nur
  Zahlen?

Zu entscheiden: die Aufteilung des Fensters und was davon live mitläuft. Der
`python-sender`-Prototyp (`.scratch/python-sender/assets/`) und dessen
Immediate-Mode-UI (`python-sender/decimen/ui.py`) sind die Vorlage; vieles
davon — Panel, Chips, Statuszeile, Farbwelt — lässt sich übernehmen.

## Answer

**Ein pygame-Fenster: links eine Seitenleiste mit Zahlen und Empfehlung,
rechts eine Live-Vorschau des aufgenommenen Bereichs. Fortschritt über
gesammelte Frames, Empfehlung nur bei schlechtem Empfang.** Aufbau und
UI-Bausteine vom `python-sender` übernommen (`decimen/ui.py`, Farbwelt, Icon).

### Während des Empfangs

- **Live-Vorschau** des Bereichs als Kachel (Q1a). Über Citrix muss man den
  Bereich nachjustieren (er ist neu aufziehbar), und dafür muss man sehen, was
  gegriffen wird — eine reine Fangrate sagt nicht, ob man 20 px daneben liegt
  oder das Citrix-Fenster gerade gescrollt ist. Der Bereich wird ohnehin
  abgegriffen, die Vorschau kostet nur einen Blit.
- **Fortschritt über gesammelte Frames, nicht gelöste Blöcke** (Q3). Der Code
  warnt ausdrücklich (`shared/fountain.ts`, Kommentar an `resolve`): die
  Peeling-Kaskade löst Blöcke hockeystick-artig am Ende, während Frames linear
  ankommen — ein Block-Balken sieht aus, als hinge er, dann springt er. Der
  Balken zeigt „gesammelt N von ~K·1,15".
- **Statistik:** Fangrate (brauchbare neue Frames/s), gemessene **px/Modul**,
  K, blockLen, Grid-Anzahl, erkannte Kompression, Dateiname sobald der
  Container ihn hergibt, geschätzte Restzeit. Für „brauchbar" zählt
  `frames_new` minus `frames_redundant` — der `LTDecoder` führt beide, und der
  rohe Wert bläht die Anzeige auf einem verlustreichen Grid-Lauf um genau den
  Redundanz-Anteil auf (96 % gezeigt vs. ~50 % real, im TS-Kommentar gemessen).

### Die Empfehlung — nur bei schlechtem Empfang (Q2a)

Läuft es gut, erscheint nichts. Bleibt die Fangrate über einige Sekunden unter
einer Schwelle, taucht **eine Zeile** mit konkreten Sender-Einstellungen auf,
abgeleitet aus der gemessenen px/Modul (Ticket „Citrix-Robustheit"): Ziel ≥6,
Hebel in der Reihenfolge weniger Bytes/Frame → weniger Grid-Codes → höhere ECC.
Die gemessene px/Modul steht als Begründung dabei, damit die Zeile nicht wie
geraten wirkt. Nie Citrix-Einstellungen.

Die px/Modul rechnet der Empfänger selbst: die Modulzahl kommt aus der
Kantenlänge des dekodierten Codes (zxing liefert die Position), die Breite je
Code aus der Bereichsbreite geteilt durch die Grid-Spalten.

### Am Ende

- **Datei über einen Speicherdialog** (Charting Q10: gefragt, wohin), SHA-256
  vor dem Anbieten verifiziert. Auf macOS derselbe `osascript`-Weg wie der
  Dateidialog des Senders (`choose file name`), auf anderen Plattformen der
  Fallback-Speicherort.
- **Textschnipsel** im Fenster angezeigt, zum Kopieren.
- Verifiziert der SHA-256 **nicht**, wird das gemeldet statt die Datei
  angeboten — der einzige Fall, in dem der Empfänger einen vollständigen
  Transfer verwirft.

### Nicht im Fenster

Vorschau der Datei, Video-Wiedergabe — bleiben out of scope (Karte, Q5). Der
Live-Ausschnitt zeigt den *aufgenommenen Bereich*, nicht die *empfangene
Datei*; das ist keine Dateivorschau, sondern ein Zielhilfe.
