# Verpackung: uv, Startbefehl, CLI, README

Type: task
Status: open
Blocked by: 07

## Question

Den Ordner so schließen, dass er das Versprechen der Karte einlöst:
irgendwohin kopieren, `uv sync`, starten — ohne Node, ohne npm.

**Eine Minimal-`pyproject.toml` liegt bereits** — angelegt in „Protokoll nach
Python portieren", weil dessen Feldversuch sonst nicht startbar war. Sie hat
die drei Laufzeitabhängigkeiten, `package = false`, `.python-version` 3.13 und
`python-preference = "only-managed"`. Was hier noch fehlt, ist alles andere:
Startbefehl, CLI, README, Repo-Verweise, und ein eingechecktes `uv.lock`.

- `pyproject.toml` mit den Abhängigkeiten aus Ticket 01 und 02 und einer
  gepinnten Python-Mindestversion; `uv.lock` mit eingecheckt, sonst ist
  „kopieren und `uv sync`" nicht reproduzierbar.
- Ein Startbefehl, kein Pfad-Gefummel: `uv run decimen-send`.
- **Das verwaltete Python erzwingen.** Homebrews `python@3.13` bringt kein
  tkinter mit (eigenes Formel-Paket), das von uv verwaltete schon, mit Tk 9.0
  — gemessen in Ticket „Fenster-Toolkit". Greift uv auf einer
  Entwicklermaschine ein vorhandenes Homebrew-Python ab, startet das
  Programm nicht. Das muss die Projektkonfiguration festlegen, nicht der
  Zufall.
- CLI-Argumente als Abkürzung in dieselbe GUI (Charting-Session Q18):
  `uv run decimen-send bericht.pdf --fps 24`. Das Fenster öffnet sich
  vorkonfiguriert; die Argumente sind kein zweiter, kopfloser Betriebsmodus.
- README im Ordner: was es ist, wie man es startet, wie man den
  Konformitätstest ausführt — und der Hinweis, dass er nach jeder Änderung
  an `shared/fountain.ts`, `shared/protocol.ts` oder
  `shared/frame-capacity.ts` fällig ist, weil er nicht in CI läuft (Q15).
- Ein Verweis aus dem Haupt-README und aus `docs/technical/architecture.md`,
  damit der zweite Sender nicht unentdeckt im Repo liegt.

Erledigt, wenn der Ordner in ein leeres Verzeichnis auf einer Maschine ohne
Node kopiert, mit `uv sync` eingerichtet und gestartet werden kann und ein
Handy empfängt.
