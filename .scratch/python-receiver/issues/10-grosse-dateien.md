# Verhalten bei sehr großen Dateien

Type: task
Status: open
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
