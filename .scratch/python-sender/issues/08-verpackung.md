# Verpackung: uv, Startbefehl, CLI, README

Type: task
Status: resolved
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

## Answer

**Der Ordner löst das Versprechen ein: kopieren, `uv sync`, `uv run decimen-send`.**

Abnahme durchgeführt, nicht behauptet. `python-sender/` ohne `.venv` und ohne
`__pycache__` in ein leeres Verzeichnis kopiert — **220 KB, 21 Dateien** — und
dort mit einem `PATH` eingerichtet, auf dem `node`, `npm` und `npx` auf
`/usr/bin/false` zeigen:

```
uv sync                             richtet ein
uv run decimen-send --help          Startbefehl da
uv run python tests/test_conformance.py     425 Prüfungen bestanden
uv run decimen-send probe.txt --fps 24 --bytes 1465 --codes 2
```

Der letzte Aufruf lief wirklich: Hauptprozess, elf Arbeiter und ein
`caffeinate -di -w 72104` daran. Dass die Schlafsperre existiert, beweist
nebenbei, dass das Datei-Argument geladen und den Strom gestartet hat — sie
wird nur im Neustart gesetzt. Nach einem `kill` waren Hauptprozess, Arbeiter
**und** `caffeinate` verschwunden; das `-w`-Flag hält, wo ein `finally`-Block
bei SIGTERM nicht mehr läuft.

Das Handy ist an demselben Code bereits zweimal bestätigt worden — beim
Feldversuch der Portierung und bei der Abnahme des Sender-Fensters. Die Kopie
ist byteweise derselbe Code; was hier zu zeigen war, ist die Verpackung.

### Was dazugekommen ist

**Einstiegspunkt.** `[project.scripts] decimen-send = "decimen.app:main"`, mit
hatchling als Build-Backend. Dafür musste `package = false` weichen — ohne Bau
gibt es kein Konsolenskript. uv installiert das Projekt editierbar, Änderungen
wirken also sofort.

**CLI als Abkürzung, nicht als zweiter Betriebsmodus.** `--fps`, `--bytes`,
`--ecc` und `--codes` akzeptieren ausschließlich Werte, die auch in der
Bedienleiste stehen; `--size` wird auf den Reglerbereich geklemmt und auf
50er-Schritte gerundet. Ein Tippfehler wird abgewiesen, **bevor** ein Fenster
aufgeht, und `--help` öffnet keines. Vier Abweisungen prüft der Rauchtest.

**Laufzeitabhängigkeiten von drei auf zwei.** Pillow wird nur noch von der
Dekodierprobe im Konformitätstest gebraucht und ist in die
Entwicklungsgruppe gewandert, zusammen mit `zxing-cpp`. Übrig bleiben `segno`
und `pygame-ce`, plus `pyobjc-framework-cocoa` nur auf macOS fürs Dock-Icon.

**Die Begründung für `only-managed` stimmt jetzt.** Sie stand für tkinter, das
es nicht mehr gibt. Die Zeile bleibt, aber wegen Reproduzierbarkeit: uv bringt
überall denselben Interpreter mit, ein System-Python nicht.

**pygames Begrüßung abgeschaltet** (`PYGAME_HIDE_SUPPORT_PROMPT` in
`decimen/__init__.py`, vor jedem Import). Ein Kommandozeilenwerkzeug, das seine
eigenen Fehler nach stdout schreibt, sollte dort nicht mit einer Fremdmeldung
anfangen.

**README im Ordner** — was es ist, wie man es startet, die CLI, was es nicht
kann, die Messwerte, die Plattformlage, und der Aufbau. Mit dem Hinweis, dass
der Konformitätstest **nicht in CI läuft** und nach jeder Änderung an
`shared/fountain.ts`, `shared/protocol.ts` oder `shared/frame-capacity.ts`
fällig ist, weil eine Drift dort nirgends eine Ausnahme wirft.

**Verweise** aus dem Haupt-README (Abschnitt „Sending without Node") und aus
`docs/technical/architecture.md` (Abschnitt „Second sender").
