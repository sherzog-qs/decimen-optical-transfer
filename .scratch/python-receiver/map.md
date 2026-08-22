# Karte: Python-Empfänger (Bildschirmbereich)

Label: `wayfinder:map`

## Destination

Ein Ordner `python-receiver/` im Repo, standalone (`uv sync`,
`uv run decimen-receive`): man zieht einmal einen Bildschirmbereich auf (wie
Cmd+Shift+4), und das Programm wertet **live aus, was in diesem Bereich ist** —
gleichgültig, was darunter liegt (Citrix-Fenster, VM, Video, lokaler Sender).
Es dekodiert den Fountain-Strom (auch Grids mit 2/4/6 Codes), zeigt während des
Empfangs Fortschritt und Statistik, empfiehlt bei schlechtem Empfang
Sender-Einstellungen, und speichert am Ende die Datei über einen Dialog bzw.
zeigt einen Textschnipsel an.

Erreicht ist das Ziel, wenn eine Datei, die `decimen-send` **durch eine
Citrix-Sitzung hindurch** zeigt, SHA-256-verifiziert herausfällt.

## Notes

**Ausführung gehört zu dieser Karte** — wie bei `python-sender/`. Endet nicht
bei einer Spezifikation, sondern beim lauffähigen Ordner.

**`python-sender/` ist die Vorlage.** Aufbau, Stil, Werkzeugkette (uv, pygame,
segno-Analogon), die Karte darüber (`.scratch/python-sender/`) und ihre
Lehren gelten hier genauso. Insbesondere: Immediate-Mode-UI in pygame, alles
in einem Prozess, `caffeinate -w`, `only-managed` Python, Konformitätstest
lokal statt in CI.

**Domäne:** unverändert — `docs/technical/protocol.md`,
`docs/technical/golden-vectors.md` (inkl. des Abschnitts „Fountain carousel",
den der Sender hinzugefügt hat), `docs/technical/architecture.md`. Die
Empfangsseite von `receive/` und `shared/` ist die Vorlage für die Portierung.

**Zwei Probleme, nicht eins.** Der Sender hatte nur das Wire-Format. Der
Empfänger hat es auch — die **Decode-Hälfte**: `parseFrame`, `classifyFrame`,
`LTDecoder`, `unpackFile`, `verifyFile`, gunzip — **plus ein Bildproblem**:
Citrix liefert keinen pixelgenauen Strom.

**Citrix ist kein Code-Pfad, sondern ein Bildqualitäts-Fall.** Der Empfänger
ist Citrix-agnostisch: er greift einen Bereich ab und dekodiert, was er sieht,
ohne je zu fragen, was darunter liegt. Es gibt keinen Citrix-Modus und keine
Fensterauswahl — ein Bereich, ein Decoder. Citrix zählt nur, weil HDX bewegte
Regionen als H.264/H.265 kodiert und erst nachschärft, wenn die Bewegung
aufhört — ein endloses Karussell erreicht die scharfe Stufe nie. Das senkt die
**Bildqualität** (Blockartefakte an Modulkanten, weniger Frames, womöglich
skaliert), nicht die Logik. Folge davon, und der einzige Grund, warum Citrix
auf der Karte steht: der Empfänger muss wissen, welche **Sender-Einstellungen**
(fps, Bytes je Frame, ECC, Grid) die Kompression überstehen, um sie zu
empfehlen — auf Citrix selbst hat der Nutzer wenig Einfluss. Ein lokaler Sender
ist der pixelgenaue Testfall zum Entwickeln; bestehen muss der Empfänger über
Citrix.

**Bildschirmaufnahme-Berechtigung ist Voraussetzung.** Gemessen: ohne sie
zählt macOS zwar Fenster auf, verbirgt aber Titel und liefert bei
Einzelaufnahme `kein Bild` (ganzer Bildschirm geht). Der Nutzer erteilt sie
dem Terminal, damit die Aufnahme auch in der Entwicklung prüfbar ist. Ein
**Bereich** (kein Fenster) wird aufgenommen — das umgeht Fensteraufzählung
und verborgene Titel, braucht aber dieselbe Berechtigung.

**Plattform: macOS zuerst, Portabilität als Struktur.** Gebaut und
abgenommen auf macOS. „Unabhängig wäre gut" (Nutzer) heißt: die Aufnahme
liegt hinter einer schmalen Schnittstelle (Bereich → RGB-Bild), sodass ein
Windows- oder Linux-Backend nachrüstbar ist, ohne Decode, UI und Fountain
anzufassen. macOS 26.5.2; `CGWindowListCreateImage` ist seit macOS 14
veraltet, `ScreenCaptureKit` der unterstützte Weg — welches Backend es wird,
misst Ticket 01.

**Standalone heißt zweite Kopie des Protokolls.** `python-sender/decimen/`
und `python-receiver/decimen/` teilen `fnv1a`, `splitmix32`, `frame_seed`,
`frame_composition`, das Container-Format. Der Nutzer hat „standalone"
zweimal gefordert — also liegt das Wire-Format bewusst doppelt (plus die
TS-Version), und der Konformitätstest muss **beide** Python-Kopien prüfen.

**Skills pro Session:** `/grilling` und `/domain-modeling` bei Entscheidungen,
`/prototype` bei Mess- und Layout-Tickets, `/tdd` für den Konformitätstest.

## Decisions so far

- [Bildschirmbereich abgreifen: welche Technik, wie schnell?](issues/01-aufnahme-technik.md) — **Quartz `CGWindowListCreateImage`, physische Pixel**, hinter der Schnittstelle `ScreenRegion` (Punkte → RGB-numpy). 123 fps, weit über Bedarf; mss raus (nur logische Punkte), ScreenCaptureKit als Upgrade-Pfad. Ende-zu-Ende belegt: grab + Konversion + zxing hält **62/s** und die Bytes stimmen mit der Quelle überein.

- [Wie viel Citrix-Kompression überlebt ein QR-Code?](issues/02-citrix-robustheit.md) — **Modul-Pixelgröße entscheidet**: ≥6 px/Modul robust, ≤3 px bricht. `px/Modul = Aufnahmebreite / (Grid-Spalten × Modulzahl)`. Stärkster Hebel: weniger Bytes/Frame (niedrigere Version, fettere Module). **Grids kehren die Sender-Logik um** — dort Durchsatz, hier Robustheitsrisiko. H.264≠HDX, also Monotonie verlässlich, Absolutwerte über echtes Citrix zu bestätigen.

- [Decode-Architektur: Aufnahme, Dedup, Grid, Fountain zusammenfügen](issues/03-decode-architektur.md) — **ein Hintergrund-Thread greift ab und dekodiert, pygame-Schleife zeigt nur an, kein Prozess-Pool**: gemessen 129 Decodes/s einthreadig im schlimmsten Fall, über jeder realen Citrix-Rate. Dedup über `seq`; Grids immer „alle Codes suchen"; Bildhash-Vorfilter als Option (Standard aus, nur pixelgenau nützlich); Stream-Neustart über die Stream-Identität vor `addFrame`.

- [Bereichsauswahl: aufziehen wie Cmd-Shift-4](issues/04-bereichsauswahl.md) — **Aufziehen auf einem eingefrorenen Vollbild-Standbild, reines pygame**, Bereich in Punkten (pygame und Bildschirm 1:1, keine Umrechnung), verifiziert bis zur Dekodierung. Während des Empfangs neu aufziehbar ohne Neustart (Decoder hängt an der Stream-Identität, nicht am Bereich). UX-Lehre: grob rahmen ist robust, pixelgenau schneidet die Ruhezone an.

- [Decode-Hälfte nach Python portieren und gegen die Vektoren festnageln](issues/05-decode-portierung.md) — **`python-receiver/decimen/` steht, dreifach belegt**: 167 Prüfungen gegen die Golden Vectors, Python↔Python über 15 % Verlust, und der **TypeScript-Encoder** → Python-Empfänger, Container rekonstruiert und SHA-256 verifiziert. `LTDecoder` mit Peeling-Kaskade, `parse_frame`/`classify_frame`/`unpack_file`/gunzip-Overflow-Schutz. Kein Encoder, kein Camera-Pfad.

- [Empfänger-Fenster: Fortschritt, Statistik, Empfehlung, Speichern](issues/06-empfaenger-fenster-design.md) — **ein pygame-Fenster**, Seitenleiste plus **Live-Vorschau** des Bereichs (zum Nachjustieren über Citrix). Fortschritt über **gesammelte Frames** (der Code warnt vor dem Block-Balken); Fangrate zählt `frames_new − frames_redundant`. Empfehlung **nur bei schlechtem Empfang**, abgeleitet aus gemessener px/Modul. Am Ende Speicherdialog, SHA-256 vor dem Anbieten verifiziert, sonst verworfen.

- [Mehrdeutige Bereiche: kein Code, oder zwei Ströme gleichzeitig](issues/09-mehrdeutige-bereiche.md) — **ein Inkumbent, Schweigen als einziger Wechselgrund**. Erkennung pro Grab (ein Grid ist *n* Codes unter einer Identität, zwei Sender je einer unter zweien), der erste geparste Frame gewinnt, fremde Frames werden verworfen statt als Reset gedeutet, Wechsel erst nach 2 s Stille — dieselbe Regel trägt den Sender-Neustart. Behob einen stummen Totalausfall: bei zwei sichtbaren Strömen setzte der Decoder in jedem Grab zurück und kam nie an.

## Not yet specified

Die drei Nebelflecken von der Kartierung sind aufgelöst — der laufende
Empfänger und die portierte Decode-Hälfte haben sie scharf genug gemacht, um
Tickets zu sein (mehrdeutige Bereiche, große Dateien, Aufnahme-Backends).

- **Kalibrierung der Schwellen an echtem HDX.** Die Empfehlung hängt an
  px/Modul ≥ 6 (Rettung) bzw. ≥ 8 (Aufwärtsrat). Beide stammen aus einer
  H.264-Simulation, die „Citrix-Robustheit" selbst als über echtes HDX zu
  bestätigen markiert hat. Ob nachjustiert werden muss und wie, ist erst
  spezifizierbar, wenn der Citrix-Lauf aus „Den Empfänger bauen" Zahlen
  geliefert hat.

## Out of scope

- **Kamera-Empfang.** Ausdrücklich nicht: der Empfang läuft direkt vom
  Bildschirm, nicht über eine Kamera. Das ist der bestehende `receive/`-Pfad
  der Web-App.
- **Senden.** Ist `python-sender/`.
- **Vorschau und Video-Wiedergabe im Fenster.** Q5: Fortschritt und
  Speichern, nicht die Browser-Eigenschaften des Web-Empfängers.
- **Lokalisierung.** Englisch, wie beim Sender.
