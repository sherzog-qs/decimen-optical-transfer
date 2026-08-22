# Fensteraufteilung: Bedienung und QR-Stream in einem Fenster oder zwei?

Type: prototype
Status: resolved
Blocked by: 02

## Question

Untergebracht werden müssen: Dateiauswahl mit Drag & Drop, Umschalter Datei
/ Textschnipsel, fünf Regler (fps, Frame-Bytes, ECC, Größe, Grid), die
Spec-Anzeige (K, QR-Version, ECC, Grid, gzip, übertragene Größe), der
„Nichts passiert?"-Hinweis — und der QR-Stream selbst, der so groß wie
möglich sein will, weil davon die Lesbarkeit für die Kamera abhängt.

Das ist ein Zielkonflikt: die Regler müssen während des Streams erreichbar
bleiben (Karte, Q16), aber jeder Pixel Bedienoberfläche fehlt dem QR-Code.

**Technische Hälfte ist beantwortet.** Ticket „Fenster-Toolkit" hat gemessen,
dass tkinter und pygame im selben Prozess zusammenlaufen (402 Durchläufe/s
mit beiden Ereignisschleifen), und die Arbeitsteilung festgelegt: tkinter für
die Bedienelemente, pygame für den Stream. Zwei Fenster sind damit die
Bauform, nicht mehr die Frage. Offen bleibt die Gestaltung — was ins
Bedienfenster gehört, wie groß es ist, ob das Stream-Fenster randlos oder im
Vollbild läuft, und wie es auf einen zweiten Monitor kommt.

Zu entscheiden: **ein** Fenster mit Seitenleiste, oder **zwei** Fenster —
ein kleines Bedienfenster und ein großes, verschiebbares Stream-Fenster, das
auf den Bildschirm wandert, auf den das Handy schaut. Zwei Fenster passen
zum typischen Aufbau, kosten aber Struktur.

Das Ticket wird mit einem groben, wegwerfbaren Aufbau im gewählten Toolkit
(Ticket 02) beantwortet, nicht mit einer Beschreibung — es geht darum, etwas
zu sehen und darauf zu reagieren. Der Prototyp braucht keinen echten
QR-Stream; ein Platzhalterbild in der richtigen Größe genügt.

Die Antwort nennt die gewählte Aufteilung und verlinkt den Prototyp. Sie
räumt dabei zwei Nebel-Punkte der Karte ab: die Gestalt des „Nichts
passiert?"-Hinweises und die Frage nach Vollbild und mehreren Monitoren.

## Answer

**Zwei Fenster: tkinter für die Bedienung, pygame für den Strom — beide
gewöhnliche Fenster mit Titelleiste.**

Prototyp: `.scratch/python-sender/assets/layout-prototype.py`. Er fährt einen
echten Karussell-Strom durch die portierten Module, nicht das im Ticketkörper
vorgesehene Platzhalterbild — die Portierung war zum Zeitpunkt des Prototyps
schon da, also gab es die höhere Auflösung umsonst.

### Das Bedienfenster

380×600, drei Abschnitte mit Trennlinien:

1. **Send** — „Choose file…" und „Text snippet" nebeneinander, darunter eine
   graue Zeile mit der aktuellen Auswahl und ihrer Größe.
2. **Transfer settings** — vier Auswahlfelder (tx fps, bytes/frame, error
   correction, layout) und ein Schieberegler für die Anzeigegröße.
3. **Stream** — die Spec-Anzeige als Paare: tx rate, frame, QR, payload,
   compression, K. Unten die Statuszeile.

Die Regler folgen der Semantik aus „Was passiert, wenn Sendeeinstellungen
mitten im Stream verstellt werden?": jede Änderung startet neu, der
Schieberegler löst an `<ButtonRelease-1>` aus statt bei jeder Rasterstufe.

### Das Stream-Fenster

**Gewöhnliches Fenster mit Titelleiste.** Kein randloser Modus, kein Vollbild.
Das Verschieben macht das Betriebssystem, die Größe kommt vom Regler. Die
Titelleiste steht zwar im Bild, stört aber keine Kamera — sie sieht nur den
Code.

**Zweiter Monitor: hinziehen, sonst nichts.** Keine gemerkte Position, keine
Monitor-Auswahl. Der Nebel-Eintrag der Karte zu Vollbild und mehreren
Monitoren ist damit abgeräumt, und zwar durch die Entscheidung, dort nichts zu
bauen.

### Der „Nichts passiert?"-Hinweis — hinfällig

**Nachtrag aus „Das Sender-Fenster bauen": den Hinweis gibt es auf der
Sendeseite nicht.** Er ist vollständig Empfänger-Sache, und ein Sender ohne
Rückkanal kann gar nicht wissen, ob etwas ankommt. Die folgende Abwägung
beantwortet damit eine Frage, die sich nicht stellt; sie steht nur noch da,
weil sie erklärt, warum die Rückfallwerte jetzt als feste Zeile ohne Timer
im Bedienfenster stehen. Siehe „Out of scope" auf der Karte.


**Als hervorgehobene Statuszeile im Bedienfenster**, nicht als eigener Dialog.

Ein Banner über dem Strom fiel technisch aus — es würde der Kamera ins Bild
ragen, also genau dorthin, wo der Hinweis behauptet, es hake. Zwischen Dialog
und Statuszeile entscheidet die Zwei-Fenster-Bauform: die Statuszeile steht
ohnehin schon da, und ein modaler Dialog über einem Bedienfenster, das man
gerade zum Nachjustieren benutzt, steht im Weg.

Zeitpolitik und Rückfallwerte kommen unverändert aus `shared/no-signal.ts` und
`shared/send-settings.ts` — kurze erste Verzögerung, längere nach dem
Wegklicken, und die Empfehlung nennt 24 fps und 1465 Bytes. Beides sind Werte,
die in den Auswahlfeldern wirklich stehen.

### Was offen bleibt und wohin es geht

Der Inhalt des Bedienfensters ist ein Prototyp, kein Urteil. Reaktionen darauf
— was fehlt, was stört, was anders gruppiert gehört — fließen in „Das
Sender-Fenster bauen", wo das richtige Fenster ohnehin entsteht. Dieses Ticket
beantwortet die Aufteilung und die Darbietung, nicht jeden Beschriftungstext.

## Nachtrag — ein Fenster statt zwei

Die Zwei-Fenster-Bauform hing an der Zweiteilung tkinter/pygame. Mit der
Umstellung auf reines pygame fällt sie: mehrere SDL-Fenster gehen nur über
`pygame._sdl2.video`, eine halbprivate API, und das lohnt hier nichts.

**Es ist jetzt ein Fenster:** links eine 300 px breite Seitenleiste mit allen
Bedienelementen, rechts der QR-Bereich. Die Kamera rahmt ohnehin nur den Code,
also kostet die Leiste Bildschirmfläche und sonst nichts. Das Fenster wächst
mit der eingestellten Anzeigegröße; ohne Nutzlast steht im QR-Bereich „Drop a
file here", damit es überhaupt ein Ablegeziel gibt.

Gültig bleibt: **kein Vollbild, kein randloser Modus, keine Monitor-Auswahl**
— das Fenster wird gezogen wie jedes andere. Und der „Nichts passiert?"-Hinweis
bleibt eine feste Zeile ohne Timer, aus dem im Sender-Ticket belegten Grund.
