# Schichtwerk — Progress

Neueste oben.

## Done

- **M2 · Mitarbeiter-CRUD** — Liste (Tabelle mit Farbpunkt/Status-Badge), Detail,
  Anlegen/Bearbeiten per ModelForm. Mandantenscoping über `services.aktueller_betrieb()`
  (einmandantiger Prototyp bis M10); Abteilungsauswahl auf den Betrieb begrenzt.
  Nav-Eintrag „Mitarbeiter". 26 Tests grün (9 neu), ruff sauber.
- **M1 · Datenmodell** — Betrieb, Abteilung, Mitarbeiter (Rolle/Vertragsstunden/Farbe),
  Schichtvorlage (Zeitfenster, Nachtschicht-Logik), Schicht-Instanz (Bedarf/Offen-Status)
  + Zuweisung mit Eindeutigkeits-Constraints. Migration, factory_boy-Fabriken, Admin.
  17 Tests grün (15 neu), ruff sauber.
- **M0 · Scaffold** — Django + Produktions-Design + Auth + Übersicht/Dienstplan-Stubs. 2 Tests grün.
