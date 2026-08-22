# Mehrdeutige Bereiche: kein Code, oder zwei Ströme gleichzeitig

Type: grilling
Status: open
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
