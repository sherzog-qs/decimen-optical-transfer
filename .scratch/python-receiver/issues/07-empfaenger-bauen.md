# Den Empfänger bauen

Type: task
Status: open
Blocked by: 03, 04, 05, 06

## Question

Die Anwendung über der portierten Decode-Hälfte: Bereich aufziehen, abgreifen,
dekodieren, Fortschritt zeigen, empfehlen, speichern.

Umfang aus den vorgelagerten Tickets:

- Bereichsauswahl (Ticket 04) und Aufnahme (Ticket 01) hinter ihrer
  Schnittstelle.
- Decode-Schleife in der Architektur aus Ticket 03 (Threads/Pool, Dedup,
  Grid, Stream-Neustart-Erkennung).
- Fenster nach Ticket 06: Fortschritt, Fangrate, Restzeit,
  Sender-Reglerempfehlung, Speicherdialog, Schnipselanzeige.
- Bildschirm-Schlafsperre während des Empfangs (`caffeinate -w`, wie beim
  Sender).
- Von `python-sender` übernehmen statt neu erfinden: die UI-Bausteine, die
  Farbwelt, das Icon, die `caffeinate`- und Spawn-Behandlung.

Erledigt, wenn ein lokaler `decimen-send` neben dem Empfänger pixelgenau
empfangen wird **und** ein `decimen-send` durch eine echte Citrix-Sitzung
hindurch — SHA-256-verifiziert. Der pixelgenaue Fall beweist die Mechanik, der
Citrix-Fall das eigentliche Ziel.
