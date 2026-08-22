# Verhalten bei sehr großen Dateien

Type: task
Status: resolved
Blocked by: —

## Question

Aus dem Nebel gehoben, weil ein laufender Empfänger existiert und die Frage
damit messbar statt spekulativ ist.

Der `LTDecoder` hält **alle gelösten Blöcke im Speicher** (`_solved`, k
Einträge à `block_len`), dazu die noch nicht auflösbaren Frames in `_by_block`.
Bei einer 64-MB-Datei ist das die gleiche Frage, die der Sender hatte — nur
kommt hier noch der Container hinzu: `assemble()` baut die volle Nutzlast, dann
entpackt `unpack_file` gzip in einen **weiteren** Puffer, und `verify_file`
hasht ihn. Drei Kopien derselben Datei können gleichzeitig leben.

Zu messen, nicht zu raten:

1. Spitzenspeicher über den Engine-Test bei 1, 8, 64 MB — wo die Kurve knickt
   und ob es die erwarteten drei Kopien sind.
2. Ob `frames_needed` und die Fortschrittsanzeige bei großem k noch stimmen
   (`k * 1.15` gerundet, u16 deckelt bei 65535 Blöcken — `frame_capacity` weiß
   das, das Fenster zeigt es nicht).
3. Was der Empfänger tun soll, wenn es nicht passt: melden bevor er anfängt
   (die Header-Werte `k`, `blockLen`, `totalLen` liegen ab dem ersten Frame
   vor), oder erst wenn es klemmt.

Erledigt, wenn die Zahlen im Ticket stehen und entweder belegt ist, dass 64 MB
durchgeht, oder die Grenze benannt und im Fenster sichtbar ist.

## Answer — 64 MB geht, ohne Sonderbehandlung

Gemessen statt geschätzt: `assets/large-file-memory.py`, Decode-Hälfte allein
(LTDecoder → `assemble` → `unpack_file` → `verify_file`), bei 2953 B je Frame.
Zwei Modi — *direct* füttert jeden Quellblock genau einmal (der billigste Weg
zur Vollständigkeit, hält nie einen wartenden Frame), *fountain* füttert den
echten Karussell-Strom des Senders mit 15 % Verlust, sodass Frames mit Grad > 1
in `_by_block` liegenbleiben. Das ist der Fall, nach dem das Ticket fragt.

|  | 1 MB | 8 MB | 64 MB |
|---|---|---|---|
| k | 358 | 2 863 | 22 897 |
| Peel-Spitze (fountain) | 2,1 MB | 16,4 MB | 132 MB |
| Gesamtspitze | 4,1 MB | 32,4 MB | **260 MB** |
| Faktor zur Datei | 4,1× | 4,0× | **4,1×** |
| Peel-CPU | 0,7 s | 9,6 s | 71 s |
| schlimmster Einzel-Frame | — | — | **103 ms** |

**Es gibt keinen Knick.** Der Verbrauch ist linear, konstant 4,1× die Datei
(3,1× ohne wartende Frames). Die drei Kopien aus der Vermutung sind real —
gelöste Blöcke, `assemble`, entpackte Datei — plus die wartenden Frames, die
die vierte ausmachen. Bei 64 MB, dem Maximum des Containers
(`MAX_FILE_BYTES`), sind das 260 MB. Auf jeder Maschine, die den Empfänger
überhaupt startet, ist das kein Thema.

**Die Blockgrenze bindet nie.** `k` ist auf dem Draht u16, bei 2931 B je Block
also 183 MB — weit über den 64 MB, die der Container zulässt. Bei 500-B-Frames
läge sie bei 30 MB, aber ein solcher Strom kann gar nicht entstehen: der Sender
prüft `fits_in_one_stream`, bevor er sendet. Der Empfänger kann nichts
empfangen, was seine eigene Grenze reißt — **hier ist nichts zu bewachen.**

**Der Peel stiehlt dem Aufnahme-Thread nichts Nennenswertes.** 71 s CPU klingt
viel, verteilt sich aber über eine Übertragung, die bei 120 kB/s mindestens
9 Minuten dauert — rund 14 % eines Kerns. Entscheidender ist die Spitze, weil
Aufnahme, Dekodierung und Peel sich einen Thread teilen (Entscheidung aus
„Decode-Architektur"): der **schlimmste einzelne Frame kostet 103 ms**. Das
sind gut sechs verpasste Aufnahmen, die der Fountain-Strom ohnehin nachliefert.
Keine mehrsekündige Kaskade, kein Grund für einen zweiten Thread.

**Also keine Grenze, kein Wächter, keine Warnung.** Die faulste Antwort, jetzt
belegt. Ergänzt wurde nur, was fehlte, um überhaupt zu sehen, worauf man
wartet: `total_len` steht ab dem ersten Frame im Header, die Seitenleiste zeigt
ihn jetzt als **size** (`human_bytes`). Vorher konnte man 20 Minuten auf eine
Datei warten, ohne zu wissen, wie groß sie ist.

Nicht gemessen: der Weg durch die Aufnahme (zxing je Frame) bei großem k — der
ist je Frame konstant und von der Dateigröße unabhängig, das hat
„Decode-Architektur" schon abgehandelt.
