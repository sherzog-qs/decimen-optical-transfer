# Das Sender-Fenster bauen

Type: task
Status: claimed
Blocked by: 02, 04, 05, 06, 09

## Question

Die Bedienoberfläche über dem portierten Protokoll, in der in Ticket 05
festgelegten Aufteilung und dem in Ticket 02 gewählten Toolkit.

Umfang (Karte, Q10/Q16/Q17):

- Datei **und** Textschnipsel als Eingabe, Datei auch per Drag & Drop.
- Fünf Regler — fps, Frame-Bytes, ECC, Anzeigegröße, Grid — im laufenden
  Stream verstellbar, mit dem in Ticket 04 festgelegten Verhalten. Die
  Wertelisten kommen aus `shared/send-settings.ts`, nicht aus neuer
  Erfindung.
- Spec-Anzeige: K, QR-Version, ECC, Grid-Anzahl, ob gzip griff, übertragene
  Größe.
- „Nichts passiert?"-Hinweis nach der Zeitpolitik aus `shared/no-signal.ts`,
  der auf die dort benannten Rückfallwerte zeigt (24 fps, 1465 Bytes) — die
  stehen in `send-settings.ts` und dürfen nicht abdriften.
- Bildschirm-Schlafsperre während des Streams (`caffeinate` auf macOS, siehe
  Plattform-Annahme der Karte).
- **Prozess-Pool und Vorratspuffer von Anfang an** (siehe „Kodieren über einen
  Prozess-Pool verteilen?"): 12 Arbeiter, die das fertige RGB-Raster
  zurückgeben, Vorrat 24–32 Frames, `pool.map` für die Reihenfolge. Bei jedem
  Neustart wird der Pool verworfen und neu aufgesetzt (83 ms), und der
  `generation`-Zähler muss die Ergebnisse des abgelösten Pools wegwerfen.
- Live erzeugen, nicht vorrendern. Bleibt die erreichte Bildrate hinter der
  eingestellten zurück, wird das angezeigt statt verschwiegen — sonst dreht
  man an einem Regler, der nichts mehr bewirkt.

Erledigt, wenn eine Datei per Drag & Drop hineinfällt, der Stream läuft, ein
Handy sie empfängt, und das Nachjustieren der Regler am laufenden Stream
funktioniert.

## Stand — gebaut, wartet auf Drag & Drop und ein Handy

Wie beim Portierungs-Ticket sagt das Abnahmekriterium mehr, als ein
automatischer Test leisten kann: eine Datei muss **hineinfallen**, ein **Handy**
muss sie empfangen, und die Regler müssen sich **am laufenden Strom**
nachjustieren lassen. Bis das jemand getan hat, bleibt das Ticket beansprucht.

### Was liegt

```
python-sender/decimen/
  send_settings.py   die kanonischen Wertelisten, Spiegel von send-settings.ts
  pool.py            FrameSource: 12 Arbeiter, Vorrat aus einem Speicherbudget
  app.py             die beiden Fenster und die Schleife
  __main__.py        python -m decimen
python-sender/tests/
  smoke_window.py    Start, Strom, Reglerwechsel, Kapazitätsfehler, Abbau
```

### Gemessen im Rauchtest

```
Start              56 ms   QR v40  Skalierung 4  K = 1
60 Frames         549 ms   (109,4 fps ungebremst)  Fenster 740x740
Reglerwechsel      70 ms   QR v27  frame 1465 B x4
Kapazitätsfehler   abgefangen, Datei behalten, nennt 1465 B/Frame
```

109 fps ungebremst bei einem v40-Code — deutlich über den 60 fps, die die
Einstellung überhaupt anbietet. Der Pool tut, was er soll: der Sender ist nicht
mehr der Engpass. Der Neustart nach einem Reglerwechsel kostet 70 ms, wie in
„Kodieren über einen Prozess-Pool verteilen?" vorhergesagt.

### Vier Dinge, die der Bau selbst herausgefunden hat

**1. Der „Nichts passiert?"-Hinweis gehört nicht hierher.** Er ist vollständig
Empfänger-Sache: `NoSignalHintTimer` wird nur von `receive/main.ts` importiert,
die Element-IDs liegen in `receive/index.html`, und `NO_SIGNAL_HINT_*` steht
nur deshalb in `send-settings.ts`, damit die Empfehlung des **Empfängers**
keinen Wert nennt, den der Sender nicht anbietet. Es geht auch gar nicht
anders — ein Sender ohne Rückkanal kann nicht wissen, ob etwas ankommt. Gebaut
ist stattdessen eine feste Zeile mit denselben Rückfallwerten, ohne Timer und
ohne Wegklicken. Siehe „Out of scope" auf der Karte.

**2. Der Einstiegspunkt darf die GUI nicht auf Modulebene importieren.** macOS
spawnt Arbeiterprozesse, indem es das `__main__`-Modul des Elternprozesses neu
importiert. Ein `from .app import main` ganz oben in `__main__.py` hätte pygame
und tkinter in alle zwölf Arbeiter gezogen — bei jedem Neustart, für Code, den
kein Arbeiter je aufruft. Der Import steht jetzt innerhalb des
`if __name__ == "__main__"`-Blocks.

**3. `run()` braucht `try/finally`.** Eine Ausnahme in der Schleife ließ zwölf
Arbeiter und ein `caffeinate` zurück, und der Prozess kam nie zum Ende — im
Rauchtest zuerst als Zehn-Minuten-Hänger aufgetreten. Zusätzlich fängt `_draw`
jetzt einen `BrokenProcessPool` ab und sagt es in der Statuszeile, statt
abzustürzen.

**4. `caffeinate -w <pid>` statt `terminate()` im `finally`.** Ein `finally`
läuft bei SIGTERM nicht, und ein zurückgelassenes `caffeinate` hält die
Maschine unbegrenzt wach. Mit `-w` wartet es auf unseren Prozess und geht mit
ihm — unabhängig davon, wie wir sterben. Nachgeprüft: nach einem `pkill` bleibt
keines übrig.

### Was noch fehlt

```
cd python-sender
uv run python -m decimen
```

Zu prüfen ist genau das, was kein Test kann:

1. Eine Datei auf das **Stream-Fenster ziehen** — sie soll sofort losgesendet
   werden (`pygame.DROPFILE`, im Rauchtest nicht auslösbar).
2. Ein **Handy** auf `https://decimen.app/receive/` soll sie empfangen.
3. Während der Strom läuft **an den Reglern drehen** — jede Änderung startet
   neu, der Schieberegler erst beim Loslassen.

Klappt das, ist das Ticket gelöst und nur noch die Verpackung offen.
