# Schichtwerk — Progress

Neueste oben.

## Done

- **M5 · Einteilen** — Das Wochengitter ist jetzt bearbeitbar. Jede Tageszelle
  führt über eine `.shift-add`-Schaltfläche zur Einteilen-Seite eines Mitarbeiters
  an einem Tag: dort werden bestehende Zuweisungen mit Entfernen-Knopf gelistet und
  eine noch freie Schichtvorlage hinzugefügt. Die Zuweisungs-Logik
  (`services.einteilen`) legt die Tagesschicht per `get_or_create` an und ist
  idempotent (keine Doppelzuweisung). Unterbesetzte Schichten (Zuweisungen < Bedarf)
  erscheinen als eigene `tfoot`-Spur „Offene Schichten" im Gitter
  (`offene_schichten_je_tag`, eine `Count`-Annotation statt N+1). Views sind
  login-geschützt, mutieren nur per POST und sind auf den Betrieb gescoped
  (fremde Mitarbeiter/Vorlagen/Zuweisungen → 404, kaputtes Datum → 404). Nebenbei
  `aktueller_betrieb()` deterministisch nach `id` gemacht. 77 Tests grün (22 neu),
  ruff sauber.

- **M4 · Dienstplan-Wochengitter** — Wochentabelle „Mitarbeiter × Wochentage" (Mo–So)
  auf dem `.sched`-Design: Kopfzeile mit Tageskürzel/Datum (heute hervorgehoben),
  je aktivem Mitarbeiter eine Zeile mit Farbpunkt, Schicht-Chips pro Tag (nach
  Beginn sortiert, Farbe der Vorlage). Wochen-Navigation per `?start=`-Parameter
  (←/Heute/→); kaputte URL fällt sicher auf die laufende Woche zurück. Gitter-Aufbau
  in `services.wochengitter` herausgelöst und ohne HTTP testbar; eine Sammelabfrage
  statt N+1. Empty State, wenn noch keine aktiven Mitarbeiter da sind. 55 Tests grün
  (16 neu), ruff sauber.

- **M3 · Schichtvorlagen-CRUD** — Liste (Name/Farbpunkt, Zeitfenster, Dauer in h,
  Abteilung, benötigte Rolle), Detail (mit Nachtschicht-Badge), Anlegen/Bearbeiten
  per ModelForm und Löschen (POST-only, Bestätigungsdialog). `SchichtvorlageForm`
  begrenzt Abteilungen auf den Betrieb, setzt ihn beim Speichern und weist eine
  Dauer-0-Vorlage (Beginn = Ende) ab; Nachtschichten über Mitternacht bleiben gültig.
  Nav-Eintrag „Schichtvorlagen". 39 Tests grün (13 neu), ruff sauber.
- **M2 · Mitarbeiter-CRUD** — Liste (Tabelle mit Farbpunkt/Status-Badge), Detail,
  Anlegen/Bearbeiten per ModelForm. Mandantenscoping über `services.aktueller_betrieb()`
  (einmandantiger Prototyp bis M10); Abteilungsauswahl auf den Betrieb begrenzt.
  Nav-Eintrag „Mitarbeiter". 26 Tests grün (9 neu), ruff sauber.
- **M1 · Datenmodell** — Betrieb, Abteilung, Mitarbeiter (Rolle/Vertragsstunden/Farbe),
  Schichtvorlage (Zeitfenster, Nachtschicht-Logik), Schicht-Instanz (Bedarf/Offen-Status)
  + Zuweisung mit Eindeutigkeits-Constraints. Migration, factory_boy-Fabriken, Admin.
  17 Tests grün (15 neu), ruff sauber.
- **M0 · Scaffold** — Django + Produktions-Design + Auth + Übersicht/Dienstplan-Stubs. 2 Tests grün.
