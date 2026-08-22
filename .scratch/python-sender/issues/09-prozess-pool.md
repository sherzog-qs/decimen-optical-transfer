# Kodieren über einen Prozess-Pool verteilen?

Type: grilling
Status: resolved

## Question

Der Durchsatz ist gemessen und liegt bei **151 KB/s**, in jedem Aufbau
gleich, weil das Kodieren **92 % der Zeit** frisst (Ticket „Fenster-Toolkit:
welche Bildrate hält es auf macOS"). Anzeige und Rasterung sind
zusammengenommen unter 8 %. Es gibt also genau eine Stellschraube.

Frames sind unabhängig: `frameIndices(k, cdf, sessionId, seq)` leitet alles
aus `seq` ab, kein Zustand wandert von Frame zu Frame. Ein
`ProcessPoolExecutor` könnte die Frames `seq..seq+n` gleichzeitig auf allen
Kernen kodieren und in einen Puffer legen, aus dem die Anzeigeschleife
sie nur noch abholt. Auf einer Maschine mit acht nutzbaren Kernen wäre das
grob das Sechs- bis Achtfache — also die Größenordnung des Web-Senders
(418,5 KB/s Desktop→Handy).

Zu entscheiden:

1. **Reicht 151 KB/s?** Zum Vergleich: der Web-Sender hält Handy→Handy
   199,2 KB/s. Eine 10-MB-Datei braucht bei 151 KB/s gut eine Minute. Wenn
   das reicht, ist das Ticket in einem Satz erledigt und der Sender bleibt
   einfach.
2. **Falls nicht: was kostet der Pool an Struktur?** Ein Vorratspuffer
   zwischen Erzeugung und Anzeige, ein Prozess-Pool, der beim Start und bei
   jeder Einstellungsänderung neu aufgesetzt werden muss, und die
   Startverzögerung von `spawn` auf macOS (kein `fork` bei Python 3.14+,
   jeder Arbeiterprozess importiert segno neu). Dazu die Frage, was beim
   Verstellen der Regler mit den bereits vorproduzierten Frames geschieht —
   die hängt an „Was passiert, wenn Sendeeinstellungen mitten im Stream
   verstellt werden?".
3. **Oder der billigere Zwischenweg:** ein einzelner Vorrats-Thread. Segnos
   Kodierung ist reines Python und hält damit das GIL — bringt also nichts,
   solange nicht auf ein freethreaded Python (3.13t/3.14t, in `uv python
   list` verfügbar) gewechselt wird. Ob das trägt, wäre zu messen statt zu
   glauben.

Die Antwort legt fest, ob der Sender einthreadig bleibt, und falls nicht,
welche der drei Bauformen es wird.

## Answer

**Ja — der Sender bekommt von Anfang an Vorratspuffer und Prozess-Pool.**

### Gemessen

Schwerster Fall: 2953 Bytes je Frame, QR v40, ECC L, auf 16 Kernen
(12 Performance, 4 Effizienz).

| | Frames/s | Nutzdurchsatz | Aufsetzen |
|---|---|---|---|
| einthreadig | 62,6 | 156 KB/s | — |
| 4 Arbeiter | 239,9 | 597 KB/s | 73 ms |
| 8 Arbeiter | 473,9 | 1180 KB/s | 73 ms |
| **12 Arbeiter** | **681,9** | **1697 KB/s** | 83 ms |
| 16 Arbeiter | 653,8 | 1627 KB/s | 104 ms |

Prüfstand: `.scratch/python-sender/assets/pool-bench.py`.

### Was daraus für den Bau folgt

**Zwölf Arbeiter, nicht sechzehn.** 16 ist messbar *schlechter* als 12 — die
vier Effizienzkerne bremsen den Verband, statt ihn zu beschleunigen. Als
Vorgabe `min(12, os.cpu_count() or 4)`. Das ist eine getunte Konstante mit
bekannter Decke, kein hergeleiteter Wert: auf anderer Hardware gehört sie
nachgemessen.

**Die Arbeiter rastern, der Hauptthread blittet nur.** Das war die eine
Entscheidung, die die Messung mitgeliefert hat. Gäben die Arbeiter nur die
Modulmatrix zurück (3,9 KB statt 1,6 MB), müsste der Hauptthread bei 682
Frames/s rund 68 % eines Kerns allein fürs Rastern aufwenden — neben tkinter
und pygame. Die Rückgabe des fertigen Rasters kostet dagegen fast nichts:
10,5× statt 10,9×. Die große IPC ist hier billiger als die kleine.

**Neustart heißt Pool neu aufsetzen.** Jede Reglerdrehung startet den Strom neu
(siehe „Was passiert, wenn Sendeeinstellungen mitten im Stream verstellt
werden?"), und die Arbeiter halten Container und Einstellungen in ihrem
Initialisierer. Den Pool zu verwerfen und neu zu bauen kostet 83 ms — akzeptabel
und viel einfacher, als den Zustand in laufende Arbeiter zu übertragen. Der
`generation`-Zähler muss die Ergebnisse eines abgelösten Pools verwerfen.

**Puffer.** Jeder Arbeiter braucht rund 16 ms je Frame, der Verband liefert
etwa 680/s. Ein Vorrat von rund zwei Frames je Arbeiter (24–32) deckt die
Latenz ab, ohne nennenswert Speicher zu binden. `pool.map` bewahrt die
Reihenfolge, was der systematische Sweep braucht — ein Empfänger, der einen
ganzen Sweep fängt, ist in genau k Frames fertig.

### Was das Ganze nicht bringt

**1697 KB/s kann kein Bildschirm zeigen.** Der Durchsatz ist
`fps × Codes × blockLen`; selbst ein 6er-Grid bei 60 fps verlangt nur 360
Frames/s. Der Pool nimmt dem Sender die Engpass-Rolle ab, mehr nicht. Danach
limitiert der Empfänger — der Web-Sender hält gemessen 418,5 KB/s
Desktop→Handy. Realistisch ist also 151 → etwa 400 KB/s, nicht 1700.

**Freethreaded Python bleibt ungemessen.** Bei 10,9× aus dem Prozess-Pool hat
es nichts beizutragen, und ob pygame-ce dafür Wheels hat, muss damit niemand
beantworten.

### Was diese Entscheidung neu aufwirft

Jeder Arbeiter hält eine eigene Kopie des Containers. Bei 64 MB und zwölf
Arbeitern sind das 768 MB allein für die Nutzlast. Das verschärft den
Nebel-Eintrag der Karte zu sehr großen Dateien deutlich und ist dort vermerkt.
