# QR-Encoder in Python: Maske pinnen, Version verriegeln, Tempo messen

Type: prototype
Status: resolved

## Question

Welche Python-Bibliothek erzeugt QR-Codes so, wie `send/qr-frame.ts` sie
erzeugt — und schafft sie das schnell genug?

`send/qr-frame.ts` ruft npm `qrcode` mit drei nicht verhandelbaren
Eigenschaften auf: **Byte-Modus** über rohe `Uint8Array`-Bytes,
**`maskPattern: 4` fest gepinnt**, und **Versionsverriegelung** — der erste
Code des Streams legt die QR-Version fest, jeder weitere muss exakt dieselbe
Geometrie liefern, weil Tiling und Grid-Rasterung das voraussetzen.

Zu klären:

1. Kann `segno` (reines Python, MIT) alle drei? `mask=`, `version=` und
   Byte-Modus existieren dem Namen nach — stimmt die Masken-Nummerierung mit
   der von npm `qrcode` überein? Ein anderer Maskenindex ist kein Fehler für
   den Decoder, bricht aber die Geometriegleichheit nicht — falsch wäre erst
   eine abweichende Version. Trotzdem prüfen: identische Eingabebytes müssen
   dieselbe Modulmatrix ergeben wie der TS-Pfad.
2. Wie schnell ist das? Die Zielrechnung ist 60 fps × bis zu 4 Grid-Codes =
   **240 Kodierungen pro Sekunde** bei 2953 Nutzbytes pro Frame (hohe
   QR-Version). Gemessen wird auf der Zielmaschine, nicht geschätzt.
3. Falls `segno` zu langsam ist: welche Alternative? Reine
   Python-Implementierungen sind der wahrscheinliche Engpass; C-gestützte
   Encoder erlauben oft kein Masken-Pinning.

Die Antwort nennt die gewählte Bibliothek, belegt die Geometriegleichheit
gegen den TS-Pfad an mindestens einem Frame, und gibt eine gemessene
Kodierrate an — aus der sich die realistisch erreichbare Bildrate ableiten
lässt (Karte, Q13: die Bildrate gibt nach, nicht die Architektur).

## Answer

**`segno` (1.6.6, reines Python, MIT).** Geprüft, nicht angenommen — über 20
Fälle (200/500/1000/1465/1850/2331/2953 Bytes × ECC L/M/Q/H):

- **20/20 Version und Geometrie identisch** mit dem TS-Pfad, auch bei
  automatischer Versionswahl. Das ist die Eigenschaft, die `qr-frame.ts`
  wirklich fordert: Tiling und Grid-Rasterung setzen voraus, dass jeder
  spätere Code dieselbe Modulzahl hat wie der erste.
- **20/20 dekodierte Bytes identisch.** Verifiziert mit `zxing-cpp` — derselben
  Decoder-Familie, die das Repo als `vendor/decimen-codec` mitbringt: aus der
  TS-Matrix und aus der segno-Matrix fällt jeweils exakt die Quellbytefolge.
- **3/20 Matrizen bitgleich** — und zwar genau die drei, in denen die Nutzlast
  die Kapazität exakt füllt (1465 L, 2331 M, 2953 L). Die Abweichung sitzt
  also ausschließlich in den Pad-Codewörtern des ungenutzten Rests und deren
  Fehlerkorrektur. Ein Decoder liest die Zeichenzahl aus dem Byte-Modus-Header
  und hört danach auf; das Padding ist für ihn unsichtbar. Für die Kamera ist
  es ein anderes Muster gleicher Größe — irrelevant.

Der Aufruf, der das leistet:

```python
segno.make(data, mode="byte", error=ecc, version=version, mask=4,
           boost_error=False)
```

**`boost_error=False` ist nicht optional.** Segnos Standard ist `True`, und
dann hebt es die Fehlerkorrektur stillschweigend an, wann immer in der
gepinnten Version Platz dafür ist: bei 10 Bytes in v15 wird aus dem
angeforderten **L ein H**, bei 400 Bytes in v20 ein **Q**. Das Symbol trägt
dann eine andere ECC-Stufe als das Protokoll festlegt
(`docs/technical/protocol.md`: „Error correction stays at L", weil In-Frame-ECC
und Fountain verschiedene Probleme lösen). Die Modulmatrix ändert sich
dadurch komplett.

Segnos Maskennummerierung stimmt mit der von npm `qrcode` überein — Maske 4
ergibt in allen 20 Fällen dieselbe Geometrie.

### Tempo

Gemessen auf der Zielmaschine, `segno.make()` allein, Maske gepinnt und
Version verriegelt:

| Frame-Bytes | QR-Version | Kodierungen/s | einzeln | 4er-Grid |
|---|---|---|---|---|
| 2953 | 40 | 60,1 | 60 fps | 15 fps |
| 1850 | 32 | 91,7 | 92 fps | 23 fps |
| 1465 | 27 | 121,2 | 121 fps | 30 fps |
| 1000 | 22 | 178,3 | 178 fps | 45 fps |
| 500 | 15 | 362,8 | 363 fps | 91 fps |

Die Zielmarke des Tickets — 240 Kodierungen/s bei 2953 Bytes — wird um das
Vierfache verfehlt. Das ist laut Karte (Q13) kein Blocker, sondern genau der
Fall, für den die Bildrate nachgibt.

Bemerkenswert: **das Produkt aus Rate und Frame-Größe ist über alle Zeilen
praktisch konstant** bei rund 177 KB/s. Segno ist byte-durchsatzgebunden, nicht
frame-gebunden — die Wahl der Frame-Größe verschiebt also nur, ob man wenige
große oder viele kleine Codes malt, nicht den Durchsatz. Nach Abzug des
22-Byte-Headers je Frame und des Fountain-Aufschlags von ~1,15× ergibt das eine
**Obergrenze von rund 150 KB/s Nutzdurchsatz**, bevor Rasterung und Anzeige
überhaupt etwas kosten.

Zur Einordnung: der Web-Sender hält 418,5 KB/s Desktop→Handy, aber nur
199,2 KB/s Handy→Handy (README, „Measured speed"). Der Python-Sender landet
damit in der Größenordnung des Handy-zu-Handy-Falls — langsamer als das
Original, aber brauchbar.

Nicht gemessen und bewusst offen gelassen: ob ein Prozess-Pool das Dach anhebt.
Frames sind unabhängig (`frameIndices` leitet alles aus `seq` ab), also ließen
sie sich über Kerne verteilen. Ob das nötig ist, entscheidet sich erst, wenn
die Anzeigekosten bekannt sind — steht als Nebel auf der Karte.

### Assets

- `.scratch/python-sender/assets/qr-reference-sweep.mjs` — erzeugt die
  Referenzmatrizen aus dem TS-Pfad (npm `qrcode` 1.5.4, wie im Lockfile).
- `.scratch/python-sender/assets/qr-reference-fingerprints.txt` — die 20
  Referenzfälle als Version, Größe und FNV, 782 Bytes. Ersetzt die
  ursprünglichen 82 KB Rohmatrizen, eingedampft durch die Entscheidung im
  Vektoren-Ticket. Die Spalte `matrixgleich` hält fest, in welchen drei
  Fällen der Fingerabdruck überhaupt vergleichbar ist.
- `.scratch/python-sender/assets/qr-conformance-sweep.py` — Vergleich und
  Benchmark. Die Grundlage für den QR-Teil des Konformitätstests in
  „Protokoll nach Python portieren".

Abhängigkeiten des Prüfstands: `segno`, `zxing-cpp`, `pillow`. Für den
Sender selbst wird nur **`segno`** gebraucht — `zxing-cpp` und `pillow`
gehören zum Test, nicht zum Programm.
