# Mehrdeutige Bereiche: kein Code, oder zwei Ströme gleichzeitig

Type: grilling
Status: resolved
Blocked by: —

## Question

Aus dem Nebel gehoben, seit die Decode-Hälfte steht und `classify_frame`
tatsächlich im Empfänger liegt: Was tut der Empfänger, wenn im Bereich nicht
genau ein Strom liegt?

Der Code beantwortet den harmlosen Fall schon und den gefährlichen nicht:

- **Kein Code im Bereich.** Nichts passiert, die Fangrate fällt, nach 4 s
  erscheint die Rettungszeile — das ist gutartig und ausreichend.
- **Fremde QR-Codes** (kein decimen-Frame). `classify_frame` liefert ein
  Verdict, `frame_verdict_message` eine Meldung. Genügt das?
- **Zwei decimen-Ströme gleichzeitig sichtbar** — der offene Fall.
  `_accept` setzt den Decoder zurück, sobald die Stream-Identität wechselt
  (`engine.py:156`). Das ist genau richtig für den *Neustart* eines Senders,
  aber bei zwei gleichzeitig sichtbaren Strömen wechselt die Identität in
  **jedem Frame**: der Decoder wird endlos zurückgesetzt, der Fortschritt
  springt, und nichts kommt je an. Stumm. Über Citrix ist das kein
  Konstruktionsfall aus der Luft — zwei Fenster, ein zu grob gezogener Bereich.

Zu entscheiden ist, was der Empfänger tun soll, nicht ob:

- **Erkennen und melden** („zwei Ströme im Bereich — Bereich enger ziehen") und
  nichts dekodieren, bis es eindeutig ist?
- **Einen Strom wählen** — den ersten gesehenen, den mit der höheren Fangrate,
  den größeren Code — und den anderen ignorieren?
- **Neustart vom Dauerwechsel unterscheiden**: ein echter Neustart wechselt die
  Identität einmal und bleibt dann; ein Doppelstrom pendelt. Ein Fenster von
  ein paar Sekunden würde beide auseinanderhalten. Wie lang, und was passiert
  in der Zwischenzeit mit den Frames?

Erledigt, wenn die Regel festgelegt ist und der Fall im Engine-Test steht —
zwei verschränkte Ströme dürfen nicht in stummem Nichtfortschritt enden.

## Answer — ein Inkumbent, und Schweigen als einziger Wechselgrund

Der Empfänger folgt **einem gewählten Strom** statt der zuletzt gesehenen
Identität. Damit fällt der Fehler weg und der Neustart bleibt erhalten — ein
Mechanismus für beide Fälle.

- **Erkennung pro Grab.** Die Codes eines Bildes werden nach `stream_identity`
  gruppiert. Ein echtes Grid ist *n* Codes unter **einer** Identität, zwei
  Sender sind je ein Code unter **zwei**. Exakt, ohne Schwelle und ohne Timer;
  ein Zeitfenster hätte nur die Symptome geglättet.
- **Der Inkumbent bleibt.** Der erste geparste Frame ernennt ihn (Q4: first
  come — Modulgröße oder Codeanzahl trennen nichts, wenn beide Sender gleich
  eingestellt sind, und eine Heuristik, die nicht trennt, ist nur eine Stelle,
  an der man später rät). Frames anderer Identität werden **verworfen**, nicht
  mehr als Reset gedeutet.
- **Wechsel nur durch Schweigen.** `STREAM_QUIET_SECONDS = 2.0`: erst wenn vom
  Inkumbenten zwei Sekunden nichts kommt, ist der Posten frei. Das ist genau
  die Signatur eines Sender-Neustarts (der alte Strom hört auf) und genau nicht
  die eines Doppelstroms (beide reden weiter). Frames des Neulings werden in
  der Wartezeit verworfen statt gepuffert — ein Fountain-Strom ist ein
  Karussell, die Blöcke kommen wieder.
- **`codes` zählt den Inkumbenten**, nicht das Bild. Nicht Kosmetik: die Zahl
  speist `recommend()`/`headroom()`, und eine 2 aus zwei getrennten Sendern
  hätte den Rat „drop the layout from 2 codes to 1" erzeugt, obwohl der Sender
  längst auf 1 steht.
- **Fremd-Verdicts nur, wenn sonst nichts dekodiert.** Neben einem laufenden
  Empfang überschrieben sie sonst in jedem Grab die Statuszeile, die der Nutzer
  gerade braucht.
- **Eine Zeile sagt es**, vor Rettung und Aufwärtsrat: „Two streams in the
  region — decoding one of them. Press Space and drag tighter around the one
  you want." Weil first come bewusst nicht rät, welchen der Nutzer meinte, muss
  die Notlösung sichtbar sein. Die Meldung ist für dieselben 2 s eingerastet,
  damit ein Nachbarcode, der in einem Grab liest und im nächsten nicht, sie
  nicht flackern lässt.

### Gemessen

`tests/test_engine.py`, 16 Prüfungen (vorher 8):

- **Doppelstrom** — beide Codes in **einem** Bild, so wie zwei Sender-Fenster in
  einem Bereich aussehen: einer der Ströme kommt vollständig und
  SHA-256-verifiziert an, `codes` meldet 1, der Bereich wird als mehrdeutig
  gemeldet. Unter der alten Regel dekodierte dieser Fall **nichts**, stumm.
- **Neustart** — A etabliert, dann sendet der Sender B: Übergabe nach 2,0 s, B
  sauber, nichts von A darin. Der alte Test schaltete sofort um; die 2 s sind
  der bewusst bezahlte Preis dafür, dass Doppelstrom und Neustart nicht mehr
  verwechselbar sind.

Kein Fall bleibt offen: kein Code im Bereich war schon gutartig (Fangrate
fällt, Rettungszeile), fremde Codes sind geregelt, zwei Ströme sind geregelt.
