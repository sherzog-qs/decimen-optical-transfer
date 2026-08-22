# Karte: Python-Sender

Label: `wayfinder:map`

## Destination

Ein Ordner `python-sender/` in diesem Repo, der nach `uv sync` mit `uv run
decimen-send` ein natives Fenster öffnet und eine Datei oder einen
Textschnipsel als Fountain-kodierten QR-Stream sendet — wire-kompatibel mit
decimen.app, ohne dass Node oder npm auf der Maschine liegen muss.

Erreicht ist das Ziel, wenn ein Handy auf decimen.app den Python-Sender
empfängt und die Datei SHA-256-verifiziert herausfällt.

## Notes

**Ausführung gehört zu dieser Karte.** Abweichend vom Wayfinder-Standard
endet sie nicht bei einer Spezifikation, sondern beim lauffähigen Ordner
(entschieden in der Charting-Session, Q4).

**Domäne:** Die Begriffe stehen schon fest und werden nicht neu erfunden —
`docs/technical/protocol.md`, `docs/technical/golden-vectors.md`,
`docs/technical/architecture.md`. Frame, Block, K, blockLen, sessionId,
Stream-Identität, Container, Grid, Snippet heißen in Python genauso wie in
TypeScript. Wer eine Portierung schreibt, liest zuerst diese drei Seiten.

**Skills pro Session:** `/grilling` und `/domain-modeling` bei
Entscheidungstickets, `/prototype` bei Mess- und Layout-Tickets, `/tdd` für
den Konformitätstest.

**Der harte Kern — korrigiert.** Diese Karte wurde in dem Glauben gezeichnet,
`dlog()` und die Soliton-Verteilung seien das Risiko. **Sind sie nicht:** sie
sind der v1-Strom und werden seit wire v2 nicht mehr gesendet (belegt in
[Woher bekommt der Python-Test seine Fountain-Vektoren?](issues/03-konformitaetsvektoren.md)).
Der Sender braucht `frameSeed`, `splitmix32`, `repairIndices` und
`frameComposition` — alles 32-Bit-Ganzzahlarithmetik, in Python mit
`& 0xFFFFFFFF` nachzubauen, keine einzige Gleitkommaoperation. Was bleibt:
Sender und Empfänger leiten jeden Frame unabhängig voneinander ab und
vergleichen nie Notizen, also ist jede Vereinfachung hier ein stiller
Totalausfall im Feld. Die Regeln stehen normativ in
`docs/technical/golden-vectors.md`, Abschnitt Fountain carousel.

**Zwei Implementierungen, ein Wire-Format.** Ab jetzt existiert das Protokoll
zweimal. Der Konformitätstest läuft bewusst nur lokal, nicht in CI
(Charting-Session, Q15) — Drift fällt also erst auf, wenn jemand ihn
ausführt. Wer `shared/fountain.ts`, `shared/protocol.ts` oder
`shared/frame-capacity.ts` anfasst, führt ihn aus.

**Angenommene Plattform: macOS.** Nicht erfragt, daher als Annahme
festgehalten: primär der Mac des Entwicklers, Portabilität wird
mitgenommen wo sie nichts kostet. Die Schlafsperre (`caffeinate`) ist der
eine bekannte Bruch. Gilt Windows oder Linux auch, kippt das Ticket 02 und
die Annahme gehört korrigiert.

**Was der Sender kann (Charting-Session Q10, Q16, Q17, Q18):** Datei und
Textschnipsel; fps, Frame-Bytes, ECC, Anzeigegröße, Grid — alle im
laufenden Stream verstellbar; Spec-Anzeige (K, QR-Version, ECC, Grid, gzip,
übertragene Größe); „Nichts passiert?"-Hinweis; Bildschirm-Schlafsperre;
Drag & Drop; CLI-Argumente als Abkürzung in dieselbe GUI.

**Live erzeugen, nicht vorrendern** (Q13). Schafft Python die 60 fps nicht,
sinkt die Bildrate — der Fountain-Code macht daraus Wartezeit, nie einen
Fehler. Vorrendern würde die Dateigröße hart begrenzen und wird nicht
gemacht.

## Decisions so far

<!-- eine Zeile je geschlossenem Ticket -->

- [QR-Encoder in Python: Maske pinnen, Version verriegeln, Tempo messen](issues/01-qr-encoder-python.md) — `segno` mit `mask=4`, `version=` und **`boost_error=False`**; Version und Geometrie in 20/20 Fällen identisch zum TS-Pfad, dekodierte Bytes ebenfalls. Tempo ist byte-gebunden bei ~177 KB/s Frame-Durchsatz → **rund 150 KB/s Nutzdurchsatz-Obergrenze**, einzelthreadig, vor Anzeigekosten.

- [Fenster-Toolkit: welche Bildrate hält es auf macOS](issues/02-fenster-toolkit.md) — **pygame-ce für den Stream, tkinter für die Bedienung, beide im selben Prozess** (geprüft: 402 Durchläufe/s mit beiden Ereignisschleifen). Ganze Kette gemessen: **151 KB/s**, davon 92 % Kodieren und nur 1,5 % Anzeige. tkinter allein würde 40–55 % des Durchsatzes kosten. Falle: Homebrew-Python hat kein tkinter, das von uv verwaltete schon.

- [Woher bekommt der Python-Test seine Fountain-Vektoren?](issues/03-konformitaetsvektoren.md) — **vier goldene Stromhashes abgeschrieben, kein Generator, kein Node**; verifiziert, dass Python sie bit-genau reproduziert. Die Regeln stehen jetzt normativ in `docs/technical/golden-vectors.md` (Abschnitt Fountain carousel). QR-Referenz auf 782 Bytes Fingerabdrücke eingedampft. gzip: byte-genau nur unkomprimiert, sonst Entscheidung plus Round-Trip; `isPrecompressedType` wird mitgepinnt.

- [Was passiert, wenn Sendeeinstellungen mitten im Stream verstellt werden?](issues/04-live-aenderung-semantik.md) — **den Web-Sender nachbauen: jede der fünf Änderungen startet den Strom neu**, mit neuer `sessionId` und `seq` auf 0. Technisch erzwungen ist das nur bei Frame-Bytes; Gleichlauf mit dem Referenz-Sender schlägt geretteten Fortschritt. Fenstergröße ändern bleibt frei, der Schieberegler löst erst beim Loslassen aus, und eine `generation`-Zählung muss die alte Renderschleife ablösen.

- [Fensteraufteilung: Bedienung und QR-Stream in einem Fenster oder zwei?](issues/05-fensteraufteilung.md) — **zwei gewöhnliche Fenster mit Titelleiste**, tkinter für die Bedienung (380×600, drei Abschnitte), pygame für den Strom. Kein Vollbild, kein randloser Modus, keine Monitor-Auswahl: der zweite Monitor wird per Ziehen erreicht. Der „Nichts passiert?"-Hinweis wird eine hervorgehobene Statuszeile im Bedienfenster, kein Dialog und kein Banner über dem Strom.

- [Kodieren über einen Prozess-Pool verteilen?](issues/09-prozess-pool.md) — **ja, von Anfang an**: 12 Arbeiter (16 ist messbar schlechter), **10,9×** auf 682 Frames/s, Pool-Aufsetzen 83 ms. Die Arbeiter geben das fertige Raster zurück, nicht die Matrix — die große IPC ist billiger als 68 % Hauptthread fürs Rastern. Danach limitiert nicht mehr der Sender, sondern der Empfänger.

- [Protokoll nach Python portieren und gegen die Vektoren festnageln](issues/06-protokoll-portierung.md) — **`python-sender/decimen/` steht und ist dreifach belegt**: 425 Prüfungen gegen die goldenen Vektoren, Round-Trip gegen den echten TypeScript-Decoder über 15 % Frame-Verlust, und ein Handy auf decimen.app, das den Strom vom Bildschirm gelesen und SHA-256-verifiziert ausgepackt hat.

## Not yet specified

- **Verhalten bei sehr großen Dateien** — bei K nahe `MAX_SOURCE_BLOCKS`
  (65535) hält Python die Nutzlast plus Blockliste im Speicher, und seit der
  Pool-Entscheidung **je Arbeiter eine eigene Kopie**: 64 MB mal zwölf sind
  768 MB allein für die Nutzlast. Ob das trägt, ob geteilter Speicher nötig
  wird oder ob der Sender eine niedrigere Grenze als 64 MB ziehen sollte,
  zeigt sich erst am laufenden Sender.
- **Schlafsperre außerhalb macOS** — nur relevant, wenn die
  Plattform-Annahme in den Notes fällt.

## Out of scope

<!-- bewusst außerhalb des Ziels; kehrt nur zurück, wenn das Ziel neu gezogen wird -->

- **Empfänger** (Kamera → WASM-Decode → Datei). Charting-Session Q3: nur
  Senden. Der teure Teil und ein eigenes Vorhaben.
- **Animations-Export** (APNG / PNG-Sequenz-ZIP). Q10: eigenständiges
  zweites Feature, nicht Teil des Live-Senders.
- **Lokalisierung, PWA-Installation, Share-Dialog, Video-Wiedergabe.** Q6:
  Englisch reicht; der Rest sind Browser-Eigenschaften ohne Entsprechung in
  einem lokalen Fenster.
- **Stabile Bibliotheks-API.** Q19: der Ordner ist ein Werkzeug. Module
  sind importierbar, aber ohne Zusage auf ihre Signaturen.
- **Der „Nichts passiert?“-Hinweis.** Beim Zeichnen der Karte als
  Sender-Funktion aufgenommen (Q17) — das war ein Lesefehler: `NoSignalHintTimer`
  gehört ausschließlich `receive/main.ts`, die Element-IDs liegen in
  `receive/index.html`. Ein Sender ohne Rückkanal kann nicht wissen, ob etwas
  ankommt, also hat der Hinweis hier nichts, worauf er auslösen könnte. Die
  Rückfallwerte stehen stattdessen als feste Zeile im Bedienfenster. Fällt mit
  dem Empfänger zusammen aus dem Ziel.
- **Konformitätstest in CI.** Q15: bleibt lokal, die GitHub-Actions-Pipeline
  wird nicht angefasst.
