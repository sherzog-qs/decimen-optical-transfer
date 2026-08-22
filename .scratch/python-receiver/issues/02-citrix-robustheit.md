# Wie viel Citrix-Kompression überlebt ein QR-Code?

Type: prototype
Status: open

## Question

Citrix liefert keinen pixelgenauen Strom (siehe Karte). Bevor der Empfänger
gebaut wird, muss klar sein, **bei welchen Sender-Einstellungen** ein Code die
Kompression überhaupt noch übersteht — denn genau darauf zielen die
Empfehlungen des Empfängers.

Ohne echtes Citrix messbar durch Simulation: ein gerasterter QR-Frame (aus
`python-sender`s `qr.py`) wird durch einen H.264-Encode/Decode-Zyklus gejagt
(`ffmpeg`, verschiedene CRF-/Bitraten-Stufen, Chroma-Unterabtastung 4:2:0),
optional skaliert, und dann mit `zxing-cpp` dekodiert. Gemessen wird die
Dekodier-Erfolgsrate über:

- **QR-Version** — kleine Frame-Bytes ergeben niedrige Versionen mit fetten
  Modulen (Version 15 bei 500 Bytes hat ~5× die Modulfläche von Version 40 bei
  2953). Die Vermutung: fette Module überleben Blockartefakte weit besser.
- **Kompressionsstärke** — CRF 23 bis CRF 40, plus ein Bitraten-gedeckelter
  Fall, der Citrix' aggressiven Modus nachstellt.
- **Skalierung** — 1:1 gegen auf krumme Größen interpoliert.
- **ECC-Stufe** — L gegen H, gegen dieselbe Nutzlast.

Wichtige Einschränkung, die in die Antwort gehört: **H.264 aus ffmpeg ist
nicht Citrix HDX.** Die Simulation zeigt die *Richtung* (fette Module gut,
hohe Versionen schlecht) verlässlich, aber die konkreten Schwellen sind
Näherungen. Der echte Beleg ist ein Messlauf über eine echte Citrix-Sitzung,
und der ist Teil der Abnahme, nicht dieses Tickets.

Die Antwort nennt die Sender-Einstellungen, die die Simulation überstehen,
als Ausgangspunkt für die Empfehlungslogik — und hält fest, dass sie über
echtes Citrix zu bestätigen sind.
