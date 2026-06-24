# Schichtwerk — Progress

Neueste oben.

## Done

- **M12 · Politur & Produktionsreife** — Finaler Durchgang, der den Prototyp
  vorzeigbar und betreibbar macht. **Niveau-gerechte Flash-Meldungen**: Das
  Layout hängt die Django-Message-Tags als CSS-Klasse an (``flash-success`` /
  ``flash-error`` / ``flash-warning``), sodass Erfolg grün und ein blockierter
  Vorgang rot erscheint statt einheitlich neutral; passende Token-Stile im
  Design-System. **Produktionsreife Settings**: ``SECRET_KEY``, ``DEBUG`` und
  ``ALLOWED_HOSTS`` kommen aus der Umgebung (``DJANGO_*``) mit dev-tauglichen
  Standardwerten — derselbe Code läuft ohne Änderung lokal und produktiv.
  **``seed_demo``-Management-Befehl**: legt idempotent einen kompletten
  Demo-Betrieb an (Login ``demo``/``demo12345``, 3 Abteilungen, 6 Mitarbeiter,
  4 Schichtvorlagen, die laufende Woche Mo–Fr teilweise besetzt mit bewusst
  offenen Schichten, plus eine Urlaubs-Abwesenheit) — ein zweiter Lauf erzeugt
  keine Duplikate. **README** mit Schnellstart, Demo-Login, Test-/Lint-Gate und
  Produktiv-Hinweisen; **requirements.txt** ergänzt. ``runserver`` startet sauber
  (Login/Registrierung/Root je HTTP 200), ``manage.py check`` ohne Befund.
  207 Tests grün (7 neu: seed_demo legt Betrieb/Login an, vollständiger
  Datengraph, offene Schichten verbleiben, Idempotenz; Flash-Klasse für
  Erfolg/Fehler/Basis), ruff sauber.

- **M11 · Stundenübersicht + Export** — Neuer Nav-Punkt „Stunden": eine
  vollständige Stunden-Tabelle je Mitarbeiter über die Woche (Mo–So pro Tag,
  Wochensumme, Vertrag und Differenz mit +/‑-Markierung), plus Tagessummen
  (Spaltensummen) und Wochengesamt. Die reine Aufbereitung liegt in
  ``services.stundenuebersicht`` (alle Zuweisungen in einer Abfrage, im Speicher
  zu (Mitarbeiter, Tag)-Stunden verdichtet — kein N+1) und ist ohne HTTP testbar;
  Wochen-Navigation wie im Dienstplan über ``?start=``. Dazu der **CSV-Export**
  des Wochenplans (``services.plan_export_zeilen`` + View ``plan_export``): je
  Zuweisung eine Zeile (Datum, Wochentag, Mitarbeiter, Rolle, Abteilung, Schicht,
  Beginn/Ende, Stunden), stabil sortiert nach Datum→Beginn→Name. Excel-DE-tauglich:
  Semikolon-getrennt, deutsches Dezimalkomma (``_stunden_dezimal``: 8,0→„8",
  7,5→„7,5"), UTF-8-BOM für korrekte Umlaute; Dateiname trägt den Wochen-Montag.
  Beide Views login-geschützt und auf den Betrieb gescoped. 200 Tests grün (21 neu:
  Stunden je Tag/Woche, Mehrfachschichten, Wochengrenze, Differenz, Tagessummen,
  Sortierung; Dezimalformat; Export-Zeilenaufbau inkl. ohne Abteilung, Wochenfilter
  und Sortierung; Stunden-View und CSV-View inkl. Header/BOM/Disposition), ruff sauber.

- **M10 · Registrierung + Onboarding** — Der Prototyp öffnet sich für mehrere
  Betriebe. Neues Modell ``accounts.Betriebszugehoerigkeit`` (OneToOne User →
  Betrieb): Die Registrierung (``RegistrierungForm`` auf Basis von Djangos
  ``UserCreationForm``) legt in einer Transaktion Login **und** eigenen Betrieb an,
  meldet direkt an und leitet ins Onboarding. ``services.aktueller_betrieb`` ist
  jetzt nutzer-bewusst: mit Zuordnung der eigene Betrieb, sonst (Altzugänge/Tests)
  unverändert der erste Betrieb — alle Views reichen nun ``request.user`` durch.
  Geführtes Onboarding (``/planung/start/``): ``onboarding_status`` baut drei
  Schritte (Mitarbeiter → Vorlage → Einteilen), jeder erledigt, sobald die Daten
  existieren; eigene Klassen ``.steps``/``.step`` auf dem Design, Fortschritts-Badge.
  Übersicht zeigt bis zum Abschluss einen Hinweis-Banner aufs Onboarding;
  Login-/Registrierungsseiten verlinken sich gegenseitig. 179 Tests grün (23 neu:
  Formular, Registrierungs-View, nutzer-bewusste Betriebsauflösung, Onboarding-Logik
  inkl. Betriebs-Scoping, Onboarding-View), ruff sauber.

- **M9 · Dashboard (echt)** — Die Übersicht zeigt jetzt echte Wochenzahlen statt
  Platzhalter. Neue Service-Funktion ``dashboard_daten`` (ohne HTTP testbar) lädt
  die Zuweisungen der laufenden Woche in einer Abfrage und verdichtet sie: vier
  KPIs (aktive Mitarbeiter, geplante Schichten der Woche, offene Schichten,
  erkannte Konflikte), Stunden je Mitarbeiter gegen die Vertragszeit (mit
  Auslastungs-Balken, Überlast > 100 % als Warn-Badge, absteigend sortiert) und
  die Tagesbesetzung Mo–So (eingeteilt/offen je Tag, heute hervorgehoben). Greift
  für Offen-Status und Konflikte auf die bestehenden Bausteine
  (``offene_schichten_je_tag``, ``regeln.wochenkonflikte``) zurück, damit die
  Übersicht dieselbe Wahrheit wie der Dienstplan zeigt. Neues Design auf dem
  System (``.dash-cols``, ``.bar``/``.bar-fill``, ``.besetzung``). 156 Tests grün
  (11 neu: leerer Betrieb, KPI-Zählung, Stunden-Summe inkl. Wochengrenze,
  Überlast-Kappung, Sortierung, Tagesbesetzung, Konflikt-KPI, View), ruff sauber.

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
