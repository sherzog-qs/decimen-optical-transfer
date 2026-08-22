# Verpackung: uv, Startbefehl, README, Repo-Verweise

Type: task
Status: open
Blocked by: 07

## Question

Den Ordner schließen — analog zu `python-sender`s Verpackungs-Ticket, dessen
Lösung die Vorlage ist.

- `pyproject.toml` mit den Laufzeitabhängigkeiten (Aufnahme-Backend aus
  Ticket 01, `zxing-cpp` fürs Dekodieren, `pygame-ce`, segno nur falls für die
  Vorschau nötig), `uv.lock` eingecheckt, `python-preference = "only-managed"`,
  Konsolenskript `decimen-receive`.
- CLI-Argumente als Abkürzung, soweit sinnvoll (z. B. ein voreingestellter
  Bereich, ein Zielordner) — kein zweiter kopfloser Modus.
- README im Ordner: was es ist, wie man es startet, die
  Bildschirmaufnahme-Berechtigung als Voraussetzung, der Citrix-Kontext, wie
  man den Konformitätstest ausführt und dass er nicht in CI läuft.
- Verweise aus dem Haupt-README und `docs/technical/architecture.md`, neben
  dem `python-sender`-Verweis.
- Der Konformitätstest muss **beide** Python-Kopien des Wire-Formats prüfen
  (Sender und Empfänger), nicht nur eine — die Kopien dürfen nicht
  auseinanderdriften.

Erledigt, wenn der Ordner in ein leeres Verzeichnis auf einer Maschine ohne
Node kopiert, mit `uv sync` eingerichtet und gestartet werden kann und über
Citrix empfängt.
