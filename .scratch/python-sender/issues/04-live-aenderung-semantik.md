# Was passiert, wenn Sendeeinstellungen mitten im Stream verstellt werden?

Type: grilling
Status: resolved

## Question

Die Einstellungen sollen im laufenden Stream verstellbar sein
(Charting-Session Q16) — aber nicht alle sind gleich harmlos.

`docs/technical/golden-vectors.md`, Abschnitt „Stream identity": Frames
gehören zum selben Transfer, wenn `sessionId`, `k`, `blockLen`, `totalLen`,
`payloadFnv` und die kritische Hälfte von `flags` übereinstimmen. Daraus
folgt:

- **fps** ändern ist folgenlos — steht in keinem Header-Feld.
- **Frame-Bytes** ändern verschiebt `blockLen` und damit `k`. Das ist ein
  anderer Stream. Der Empfänger muss zurückgesetzt werden, alle bereits
  gesammelten Blöcke sind wertlos.
- **ECC** und **Anzeigegröße** berühren den Header nicht, wohl aber die
  QR-Version — und die ist nach dem ersten Code verriegelt
  (`send/qr-frame.ts`).
- **Grid** ändert, wie viele Codes gleichzeitig auf dem Schirm stehen.

Zu entscheiden: wie verhält sich das Python-Fenster bei jeder dieser
Änderungen? Nahe liegt, es dem Web-Sender gleichzutun — dann ist erst zu
lesen, was der tut (`send/main.ts`, um Zeile 515 und die Regler-Handler),
und ob er bei `blockLen`-Änderungen eine neue `sessionId` zieht. Nahe liegt
aber auch, im nativen Fenster bewusst abzuweichen, etwa mit einer sichtbaren
Warnung „setzt den Empfänger zurück" vor der Änderung.

Die Antwort legt für jeden der fünf Regler fest, was beim Verstellen
passiert, und ob die Spec-Anzeige daraufhin welche Werte neu zeigt.

## Answer

**Den Web-Sender nachbauen: jede der fünf Änderungen startet den Strom neu.**

`send/main.ts:454` hängt alle fünf Regler an denselben Handler:

```js
for (const el of [cfgFps, cfgBytes, cfgEcc, cfgGrid, cfgSize])
  el.addEventListener("change", () => void startStream());
```

`startStream()` würfelt dabei eine **neue `sessionId`** (`Math.floor(Math.random()
* 0xffff) + 1`, also 1…65535), baut einen frischen `LTEncoder`, setzt `seq` auf
0 und lässt die QR-Version am ersten Frame neu verriegeln. Die ausgewählte
Datei bleibt erhalten — nur der Strom fängt von vorn an, und der Empfänger
damit auch.

### Was das je Regler bedeutet

| Regler | Rührt an | Verhalten |
|---|---|---|
| fps | nichts im Header | Neustart, Empfänger verliert alles |
| Anzeigegröße | nichts im Header | Neustart, Empfänger verliert alles |
| Grid | nichts im Header | Neustart, Empfänger verliert alles |
| ECC | nichts im Header, aber QR-Version | Neustart, Empfänger verliert alles |
| Frame-Bytes | `k`, `blockLen` | Neustart — hier unvermeidlich |

Nur die letzte Zeile ist technisch erzwungen; die anderen vier werfen den
Fortschritt weg, obwohl sie es nicht müssten. Das ist bewusst so entschieden:
**Gleichlauf mit dem Referenz-Sender schlägt geretteten Fortschritt.** Ein
Pfad, kein Sonderfall, und niemand muss je fragen, ob Python und Web sich hier
unterscheiden.

Die differenzierte Variante — fps, Größe und Grid greifen live, ECC verriegelt
nur die QR-Version neu, nur Frame-Bytes startet neu — wurde geprüft und
verworfen. Sie ist nicht falsch; sie ist eine Abweichung, und dieser Sender
soll keine haben.

### Was daraus für die Umsetzung folgt

**Alte Renderschleife ablösen.** `send/main.ts:121` hält einen
`generation`-Zähler, den jeder Neustart hochzählt; die laufende Schleife prüft
`gen !== generation` und beendet sich. Ohne dieses Gegenstück laufen in Python
nach fünf Reglerdrehungen fünf Schleifen gleichzeitig und malen gegeneinander.

**Der Schieberegler darf nicht bei jedem Pixel neu starten.** Die Anzeigegröße
ist im Web `<input type="range" min="300" max="1200" step="50">`, gebunden an
**`change`, nicht `input`** — im Browser feuert das erst beim Loslassen. Ein
Zug über die ganze Bahn löst also **einen** Neustart aus, nicht achtzehn.
Tkinters `Scale` ruft sein `command` dagegen bei jeder Rasterstufe auf; das
muss auf `<ButtonRelease-1>` umgehängt werden, sonst wird das Einstellen der
Größe zum Dauerneustart.

**Fenstergröße ändern ist frei.** `send/main.ts:453` hängt `window.resize` an
einen separaten `resizeDisplay()`-Rückruf, der die Leinwand neu bemisst **ohne**
Neustart. Das Ziehen am Fensterrahmen darf in Python ebenso wenig einen
Neustart auslösen — nur der Regler tut das.

**Spec-Anzeige.** Die Frage „live oder statisch" stellt sich nicht mehr: die
Werte werden beim Verriegeln der QR-Version geschrieben, und weil jede
Änderung neu verriegelt, wird die Anzeige bei jeder Änderung vollständig neu
geschrieben. Damit ist auch der gleichnamige Nebel-Eintrag der Karte erledigt.

**Kapazitätsfehler.** Sprengt die neue Frame-Größe `MAX_SOURCE_BLOCKS`
(65535), zeigt der Web-Sender einen Fehler, der die **kleinste ausreichende
Größe aus der angebotenen Liste** nennt, und **behält die Datei** — „raising
bytes/frame back up is the fix, and dropping the pick would hide that"
(`send/main.ts:497`). Ebenso nachbauen.

**Regler-Typen.** Vier Auswahlfelder mit festen Werten aus
`shared/send-settings.ts` (fps, Frame-Bytes), vier ECC-Stufen, vier
Grid-Varianten (1/2/4/6 Codes), plus der eine Schieberegler 300…1200 in
50er-Schritten. Keine freien Zahleneingaben.
