# Schichtwerk

Dienst- und Schichtplanung für kleine und mittlere Betriebe (KMU). Mitarbeiter
auf mehrere Schichten einteilen, Konflikte (Doppelbelegung, Ruhezeit,
Wochenstunden) vermeiden und die Besetzung der Woche im Blick behalten — als
übersichtliche Django-Web-App mit eigenem Produktions-Design.

## Funktionsumfang

- **Dienstplan-Wochengitter** (Kern): Mitarbeiter × Wochentage, Schichten je Tag
  zuweisen/entfernen, Wochen-Navigation, offene (unterbesetzte) Schichten markiert.
- **Mitarbeiter** mit Rolle, Vertragsstunden, Farbe und Abteilung.
- **Schichtvorlagen** (Früh/Spät/Nacht …) mit Zeitfenster und benötigter Rolle.
- **Abteilungen** verwalten und den Plan danach filtern.
- **Arbeitszeit-Regeln**: Warnungen bei Doppelbelegung, Ruhezeit < 11 h und
  Wochenhöchststunden (am ArbZG orientiert).
- **Abwesenheiten** (Urlaub/Krank) blockieren die Einteilung und sind im Gitter sichtbar.
- **Dashboard** mit echten Wochen-KPIs, Auslastung je Mitarbeiter und Tagesbesetzung.
- **Stundenübersicht** je Mitarbeiter/Woche und **CSV-Export** des Wochenplans (Excel-DE-tauglich).
- **Registrierung + geführtes Onboarding** für neue Betriebe.

## Schnellstart

Voraussetzung: Python 3.11+.

```bash
cd schichtwerk
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo      # Beispiel-Betrieb mit Daten anlegen
python manage.py runserver
```

Dann <http://127.0.0.1:8000/> öffnen.

## Anmeldung

Nach `seed_demo` steht ein fertiger Demo-Betrieb bereit:

- **Benutzer:** `demo`
- **Passwort:** `demo12345`

Alternativ über „Registrieren" einen eigenen Betrieb anlegen und dem Onboarding
folgen. Einen Django-Admin-Zugang bei Bedarf mit
`python manage.py createsuperuser` erstellen (Admin unter `/admin/`).

## Entwicklung

```bash
ruff check .          # Linting
python manage.py test # Testsuite
```

Vor jedem Commit gilt: `ruff check .` sauber **und** `python manage.py test`
vollständig grün.

## Produktivbetrieb

Sicherheitsrelevante Einstellungen kommen aus der Umgebung (Standardwerte sind
auf lokale Entwicklung ausgelegt):

- `DJANGO_SECRET_KEY` — eigener geheimer Schlüssel.
- `DJANGO_DEBUG` — `0` setzen, um den Debug-Modus auszuschalten.
- `DJANGO_ALLOWED_HOSTS` — kommagetrennte Hostliste (z. B. `app.example.com`).

## Stack

Django 5 · eigenes CSS-Design-System (`static/css/design.css`) · SQLite (Prototyp)
· factory_boy/Faker für Testdaten.
