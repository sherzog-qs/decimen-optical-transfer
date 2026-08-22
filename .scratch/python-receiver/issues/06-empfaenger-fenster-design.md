# Empfänger-Fenster: Fortschritt, Statistik, Empfehlung, Speichern

Type: grilling
Status: open
Blocked by: 03

## Question

Was zeigt das Fenster während und nach dem Empfang?

Der Umfang steht (Charting Q5, Q7-neu, Q10), die Gestalt nicht:

- **Während des Empfangs:** Fortschritt (gelöste Blöcke von K), Fangrate
  (brauchbare Frames je Sekunde), geschätzte Restzeit, erkannte
  Stream-Parameter (K, blockLen, Grid-Anzahl, Dateiname sobald der Container
  ihn hergibt). Der Fortschritt ist die einzige Rückmeldung, ob es läuft —
  gegen Citrix blind, deshalb zentral.
- **Empfehlung.** Der Empfänger sieht als Einziger die Fangrate. Bei
  schlechtem Empfang schlägt er konkrete **Sender-Einstellungen** vor — „nur
  12 %, sag dem Sender 1000 Bytes und 15 fps" — gestützt auf die Zahlen aus
  „Citrix-Robustheit". Nie Citrix-Einstellungen (darauf hat der Nutzer kaum
  Einfluss).
- **Am Ende:** Datei über einen Speicherdialog ablegen (Charting Q10:
  gefragt, wohin), Textschnipsel im Fenster anzeigen zum Kopieren. SHA-256
  wird vor dem Anbieten verifiziert.
- **Der Bereich.** Zeigt das Fenster einen Live-Ausschnitt des aufgenommenen
  Bereichs (damit man sieht, dass man den richtigen Fleck trifft), oder nur
  Zahlen?

Zu entscheiden: die Aufteilung des Fensters und was davon live mitläuft. Der
`python-sender`-Prototyp (`.scratch/python-sender/assets/`) und dessen
Immediate-Mode-UI (`python-sender/decimen/ui.py`) sind die Vorlage; vieles
davon — Panel, Chips, Statuszeile, Farbwelt — lässt sich übernehmen.
