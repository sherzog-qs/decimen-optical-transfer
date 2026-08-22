# Verpackung: uv, Startbefehl, README, Repo-Verweise

Type: task
Status: resolved
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

## Answer — der Ordner ist zu

Alles aus der Frage, in der Reihenfolge:

- **`pyproject.toml`** stand schon (Laufzeitabhängigkeiten, `uv.lock`
  eingecheckt, `python-preference = "only-managed"`, Konsolenskript
  `decimen-receive`). Nichts zu tun außer es zu belegen.
- **CLI als Abkürzung, kein zweiter Modus.** `--region X,Y,W,H` startet direkt
  auf einem Bereich statt ihn zu ziehen; `--out DIR` öffnet den Speicherdialog
  dort. Beide führen ins selbe Fenster: der Bereich bleibt mit Leertaste neu
  ziehbar, und `--out` umgeht den Dialog nicht, es verschiebt nur seinen
  Startordner (`choose file name … default location`). Beim Verdrahten fiel
  auf, dass `pick_region` den Motor selbst startete — das liegt jetzt in
  `_start_on`, sonst hätte ein voreingestellter Bereich eine zweite Kopie
  derselben fünf Zeilen gebraucht.
- **README** im Ordner: was es ist, Start, **Bildschirmaufnahme-Berechtigung
  als Voraussetzung** (samt der Falle, dass macOS sie nicht live aktiviert),
  der Citrix-Kontext mit den echten Zahlen aus dem Feldversuch, die Testliste
  und warum sie nicht in CI läuft.
- **Repo-Verweise**: Haupt-README bekommt „Receiving off a screen, without a
  camera" neben dem Sender-Abschnitt; `architecture.md` bekommt „Second
  receiver" und die Korrektur von „zwei Implementierungen" auf **drei**.
- **Beide Python-Kopien geprüft** — der eigentliche Punkt des Tickets.
  `test_the_two_python_copies_agree` ruft `fnv1a`, `splitmix32`, `frame_seed`,
  `frame_composition`, `block_length` und die Container-Konstanten **aus beiden
  Ordnern nebeneinander** auf. Vorher prüfte jeder Ordner nur sich selbst
  gegen die Vektoren; der Rundlauf durch den Sender-Encoder fing Drift nur da,
  wo die Pfade sich zufällig überschneiden. 167 → **223 Prüfungen**.

### Abnahme

Ordner nach `/tmp` kopiert (ohne `.venv`), `uv sync`, `uv run
decimen-receive --help` — läuft. Dabei kam eine Kante heraus: der
Konformitätstest brach mit einem nackten `FileNotFoundError` ab, wenn
`python-sender/` nicht danebenliegt. Der Sender ist ein **Geschwister, keine
Abhängigkeit** — die drei Gruppen, die beide Kopien brauchen, melden jetzt
„skipped" statt zu stürzen: im Repo 223 Prüfungen, in der einsamen Kopie 34.
Der Citrix-Empfang ist über „Den Empfänger bauen" belegt.
