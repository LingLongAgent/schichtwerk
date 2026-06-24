# Schichtwerk — Progress

Neueste oben.

## Done

- **M8 · Abteilungen/Standorte** — Vollständige Abteilungsverwaltung auf dem
  Design: Liste mit Zähler je Abteilung (Mitarbeiter/Vorlagen, eine
  ``Count``-Annotation statt N+1), Anlegen, Umbenennen, Löschen (POST-only). Das
  ``AbteilungForm`` setzt den Betrieb beim Speichern und prüft den Namen je
  Betrieb auf Eindeutigkeit ohne Rücksicht auf Groß-/Kleinschreibung (passend zur
  DB-Bedingung); beim Bearbeiten ist der eigene Datensatz ausgenommen. Löschen ist
  schonend: Mitarbeiter und Vorlagen behalten ihre Daten, nur ihr Abteilungsbezug
  fällt auf ``NULL`` (``on_delete=SET_NULL``). Neuer Nav-Eintrag „Abteilungen".
  Der Dienstplan lässt sich jetzt nach Abteilung filtern: neue ``.filterbar`` über
  dem Gitter (Alle + je Abteilung), ``services.abteilung_filter`` löst den
  ``?abteilung=``-Parameter robust auf (unbekannt/fremd/Unsinn → ungefiltert), das
  Wochengitter zeigt dann nur Mitarbeiter und offene Schichten dieser Abteilung.
  Die Wochen-Navigation behält den Filter bei. Views login-geschützt und auf den
  Betrieb gescoped (fremde Abteilung → 404). 145 Tests grün (20 neu: Formular,
  Filter-Auflösung, Gitter-/Offen-Filter, CRUD-Views), ruff sauber.

- **M7 · Abwesenheiten/Urlaub** — Neues Modell ``Abwesenheit`` (Mitarbeiter, Art
  Urlaub/Krank/Sonstiges, inklusiver Zeitraum ``von``–``bis``, Notiz) mit
  DB-CheckConstraint ``bis >= von`` und ``umfasst(datum)``. Die Service-Funktion
  ``ist_abwesend`` prüft den Tag; ``einteilen`` weist eine Zuweisung an einem
  Abwesenheitstag mit der neuen Ausnahme ``EinteilenBlockiert`` ab (die View fängt
  sie und zeigt eine Fehlermeldung statt einer ungültigen Einteilung). Das
  Wochengitter trägt je Tageszelle die betreffende Abwesenheit (eine Sammelabfrage
  ``abwesenheiten_je_woche`` statt N+1); im Gitter erscheint ein ``.shift.abw``-Chip
  und der Einteilen-Knopf entfällt an gesperrten Tagen. Erfassen/Entfernen erfolgt
  auf der Mitarbeiter-Detailseite (``AbwesenheitForm`` mit Datums-Validierung,
  POST-only, auf den Betrieb gescoped). Admin registriert. 125 Tests grün (24 neu:
  Modell/Grenzfälle, Service-Blockade, Gitter, Formular, Views), ruff sauber.

- **M6 · Arbeitszeit-Regeln & Konflikte** — Drei reine Prüffunktionen über
  ``Schichtzeit``-Werte (ohne DB/HTTP, am ArbZG orientiert): Doppelbelegung
  (Überlappung), Ruhezeit < 11 h zwischen Folgeschichten und Wochenhöchststunden
  (> 48 h). Grenzwerte je Aufruf überschreibbar, Nachtschichten über Mitternacht
  korrekt behandelt; ``Schicht.beginn_am``/``ende_am`` liefern die konkreten
  Zeitfenster. Der DB-Wrapper ``wochenkonflikte`` lädt die Woche in einer Abfrage
  und gruppiert je Mitarbeiter. Das Wochengitter reicht die Konflikte an die
  Oberfläche durch: Warnkarte mit Klartext je Mitarbeiter, Zähler-Badge an der
  Mitarbeiterzeile und ``.shift.warn``-Markierung der beteiligten Chips
  (``konflikt_schicht_ids``). 101 Tests grün (24 neu: 20 Regel-Logik inkl.
  Grenzfälle, 4 Gitter-/View-Integration), ruff sauber.

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
