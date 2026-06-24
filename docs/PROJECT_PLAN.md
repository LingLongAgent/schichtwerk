# Schichtwerk — Projektplan (Prototyp)

**Produkt:** Dienst-/Schichtplanung für KMU — Mitarbeiter auf mehrere Schichten
einteilen, Konflikte vermeiden, Besetzung im Blick. Repo: `LingLongAgent/schichtwerk`.
Stack: Django + eigenes Produktions-Design (`static/css/design.css`).

## Grundregeln (pro Aufgabe)
- EINEN offenen `[ ]`-Punkt auf solider Prototyp-Tiefe umsetzen. KISS, typannotiert.
- **Jede Funktion getestet** (pytest/Django-TestCase, Mockdaten via factory_boy/Faker).
- Gate vor Commit: `ruff check .` sauber UND `python manage.py test` grün. Nie rot committen.
- Commit referenziert den Punkt, **push** zu origin, zugehöriges Issue schließen.
  Haken hier setzen + Notiz in `docs/PROGRESS.md`. UI bleibt professionell/übersichtlich.

## Aufgaben
- [x] M0 · Scaffold — Design-System, Auth, Übersicht/Dienstplan-Stubs. (2 Tests grün)
- [x] M1 (#1) · Datenmodell — Betrieb, Abteilung, Mitarbeiter (Rolle/Vertragsstunden/Farbe), Schichtvorlage (Start/Ende/Abteilung), Schicht-Instanz + Zuweisung. Migrationen, factories, Tests, Admin.
- [x] M2 (#2) · Mitarbeiter-CRUD — Liste/Anlegen/Bearbeiten/Detail auf dem Design. Tests.
- [x] M3 (#3) · Schichtvorlagen-CRUD — Früh/Spät/Nacht etc. (Zeiten, Abteilung, benötigte Rolle). Tests.
- [x] M4 (#4) · Dienstplan-Wochengitter — Gitter (Mitarbeiter × Wochentage), Wochen-Navigation, Schichten anzeigen. Tests.
- [x] M5 (#5) · Einteilen — Mitarbeiter einer Schicht an einem Tag zuweisen/entfernen; offene Schichten markiert. Tests.
- [x] M6 (#6) · Arbeitszeit-Regeln & Konflikte — Doppelbelegung, Ruhezeit (<11h), Wochenhöchststunden → Warnungen. Pure Logik + Tests.
- [x] M7 (#7) · Abwesenheiten/Urlaub — je Mitarbeiter (Urlaub/Krank) blockiert Zuweisung, im Gitter sichtbar. Tests.
- [x] M8 (#8) · Abteilungen/Standorte — verwalten + Plan danach filtern. Tests.
- [x] M9 (#9) · Dashboard (echt) — KPIs (Mitarbeiter, Schichten/Woche, offene Schichten, Konflikte), Stunden je Mitarbeiter, Wochenbesetzung. Tests.
- [ ] M10 (#10) · Registrierung + Onboarding — Betrieb + Login anlegen, erste Mitarbeiter/Schichten geführt. Tests.
- [ ] M11 (#11) · Stundenübersicht + Export — Stunden je Mitarbeiter/Woche, CSV-Export des Plans. Tests.
- [ ] M12 (#12) · Politur & Produktionsreife — Validierung, Empty States, responsive, Konsistenz. Finaler Durchgang.

## Done-Log
Siehe `docs/PROGRESS.md`.
