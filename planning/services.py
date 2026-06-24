"""Hilfsfunktionen für den aktiven Mandanten und das Dienstplan-Wochengitter.

Solange Registrierung/Onboarding (M10) fehlt, arbeitet der Prototyp einmandantig:
Es gibt genau einen ``Betrieb``, auf den sich alle Ansichten beziehen.
``aktueller_betrieb`` kapselt diese Annahme an einer Stelle, damit M10 sie später
ersetzen kann, ohne dass die Views angefasst werden müssen.

Zusätzlich liegt hier die Aufbereitung des Wochengitters (M4): aus den
Zuweisungen einer Kalenderwoche wird die Tabelle „Mitarbeiter × Wochentage"
gebaut. Die Logik ist bewusst aus der View herausgelöst, damit sie ohne HTTP
isoliert getestet werden kann.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count

from . import regeln
from .models import Abwesenheit, Betrieb, Mitarbeiter, Schicht, Schichtvorlage, Zuweisung

STANDARD_BETRIEB_NAME = "Mein Betrieb"


class EinteilenBlockiert(Exception):
    """Eine Zuweisung ist fachlich nicht möglich (z. B. Abwesenheit am Tag).

    Wird von ``einteilen`` ausgelöst und in der View abgefangen, um dem Planer
    eine verständliche Meldung zu zeigen, statt eine ungültige Einteilung
    anzulegen.
    """

# Wochentags-Kürzel Mo–So für die Gitter-Kopfzeile (Index = date.weekday()).
WOCHENTAG_KUERZEL = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def aktueller_betrieb() -> Betrieb:
    """Liefert den Betrieb, in dessen Kontext gerade geplant wird.

    Existiert noch keiner (frische Installation), wird ein Standard-Betrieb
    angelegt, damit die Ansichten ohne vorheriges Onboarding nutzbar sind.
    Maßgeblich ist der zuerst angelegte Betrieb (nach ``id``), damit die Auswahl
    stabil bleibt und nicht von der alphabetischen Standard-Sortierung abhängt.
    """
    betrieb = Betrieb.objects.order_by("id").first()
    if betrieb is None:
        betrieb = Betrieb.objects.create(name=STANDARD_BETRIEB_NAME)
    return betrieb


def wochenstart(datum: date) -> date:
    """Montag der Kalenderwoche, in der ``datum`` liegt (Woche läuft Mo–So)."""
    return datum - timedelta(days=datum.weekday())


def parse_wochenstart(roh: str | None, heute: date) -> date:
    """Den Query-Parameter ``start`` zum Montag der gewünschten Woche auflösen.

    Fehlt der Parameter oder ist er kein gültiges ISO-Datum, fällt die Funktion
    auf die Woche des heutigen Tages zurück — eine kaputte URL führt damit nie zu
    einem Fehler, sondern stets zur aktuellen Woche.
    """
    if roh:
        try:
            bezug = date.fromisoformat(roh)
        except ValueError:
            bezug = heute
    else:
        bezug = heute
    return wochenstart(bezug)


def wochentage(start: date) -> list[date]:
    """Die sieben Tage (Mo–So) ab dem Wochen-Montag ``start``."""
    return [start + timedelta(days=versatz) for versatz in range(7)]


def wochengitter(betrieb: Betrieb, start: date, heute: date) -> dict:
    """Daten für das Wochengitter (Mitarbeiter × Wochentage) aufbereiten.

    Liefert je aktivem Mitarbeiter eine Zeile mit sieben Tageszellen; jede Zelle
    trägt die an diesem Tag zugewiesenen Schichten (nach Beginn sortiert). Alle
    Zuweisungen der Woche werden in einer einzigen Abfrage geladen und im
    Speicher den (Mitarbeiter, Tag)-Zellen zugeordnet, damit das Gitter keine
    N+1-Abfragen auslöst.

    Zusätzlich werden die Arbeitszeit-Regeln (M6) je Mitarbeiter ausgewertet:
    ``zeilen[i]["konflikte"]`` trägt die Verstöße der Zeile, ``konflikte`` eine
    nach Mitarbeitern gruppierte Übersicht und ``konflikt_schicht_ids`` die Menge
    der beteiligten Schichten, damit die Oberfläche die betroffenen Chips
    hervorheben kann.
    """
    tage = wochentage(start)
    mitarbeiter = list(betrieb.mitarbeiter.filter(aktiv=True))

    belegung: dict[tuple[int, date], list[Schicht]] = defaultdict(list)
    zuweisungen = Zuweisung.objects.filter(
        mitarbeiter__betrieb=betrieb,
        schicht__datum__range=(tage[0], tage[-1]),
    ).select_related("schicht__vorlage")
    for zuweisung in zuweisungen:
        belegung[(zuweisung.mitarbeiter_id, zuweisung.schicht.datum)].append(zuweisung.schicht)

    # Arbeitszeit-Regeln je Mitarbeiter prüfen (M6); die betroffenen Schicht-IDs
    # sammeln, damit die zugehörigen Chips im Gitter als Warnung markiert werden.
    konflikte_je_person = regeln.wochenkonflikte(betrieb, tage[0], tage[-1])
    konflikt_schicht_ids = {
        schicht_id
        for konflikte in konflikte_je_person.values()
        for konflikt in konflikte
        for schicht_id in konflikt.schicht_ids
    }

    # Abwesenheiten der Woche je (Mitarbeiter, Tag), damit die Zelle „Urlaub/Krank"
    # anzeigen und das Einteilen an diesen Tagen unterdrücken kann (M7).
    abwesend = abwesenheiten_je_woche(betrieb, tage)

    zeilen = []
    konflikt_uebersicht = []
    for person in mitarbeiter:
        zellen = []
        for tag in tage:
            schichten = sorted(belegung.get((person.id, tag), []), key=lambda s: s.beginn)
            zellen.append(
                {
                    "datum": tag,
                    "ist_heute": tag == heute,
                    "schichten": schichten,
                    "abwesenheit": abwesend.get((person.id, tag)),
                }
            )
        konflikte = konflikte_je_person.get(person.id, [])
        zeilen.append({"person": person, "zellen": zellen, "konflikte": konflikte})
        if konflikte:
            konflikt_uebersicht.append({"person": person, "konflikte": konflikte})

    kopf = [
        {
            "kuerzel": WOCHENTAG_KUERZEL[index],
            "datum": tag,
            "ist_heute": tag == heute,
            "ist_wochenende": index >= 5,
        }
        for index, tag in enumerate(tage)
    ]
    offen_je_tag = offene_schichten_je_tag(betrieb, tage)
    offen = [
        {"datum": tag, "ist_heute": tag == heute, "schichten": offen_je_tag.get(tag, [])}
        for tag in tage
    ]
    return {
        "start": start,
        "ende": tage[-1],
        "kopf": kopf,
        "zeilen": zeilen,
        "offen": offen,
        "hat_offene": any(spalte["schichten"] for spalte in offen),
        "konflikte": konflikt_uebersicht,
        "konflikt_schicht_ids": konflikt_schicht_ids,
        "hat_konflikte": bool(konflikt_uebersicht),
        "vorwoche": start - timedelta(days=7),
        "naechste": start + timedelta(days=7),
    }


def offene_schichten_je_tag(betrieb: Betrieb, tage: list[date]) -> dict[date, list[Schicht]]:
    """Unterbesetzte Schichten der Woche, je Tag und nach Beginn sortiert.

    „Offen" heißt: weniger Zuweisungen als ``bedarf`` — die Schicht braucht noch
    Personal. Die Zuweisungszahl wird per ``Count`` mitannotiert, damit der
    Offen-Status ohne eine Zusatzabfrage je Schicht (N+1) bestimmt werden kann.
    Nur Schichten des Betriebs im Wochenfenster werden betrachtet.
    """
    schichten = (
        Schicht.objects.filter(vorlage__betrieb=betrieb, datum__range=(tage[0], tage[-1]))
        .select_related("vorlage")
        .annotate(anzahl_zuweisungen=Count("zuweisungen"))
    )
    je_tag: dict[date, list[Schicht]] = defaultdict(list)
    for schicht in schichten:
        if schicht.anzahl_zuweisungen < schicht.bedarf:
            je_tag[schicht.datum].append(schicht)
    for schichten_am_tag in je_tag.values():
        schichten_am_tag.sort(key=lambda s: s.beginn)
    return dict(je_tag)


def ist_abwesend(person: Mitarbeiter, datum: date) -> Abwesenheit | None:
    """Die Abwesenheit liefern, die ``person`` am ``datum`` betrifft — sonst ``None``.

    Maßgeblich ist der inklusive Zeitraum ``von``–``bis``. Existieren mehrere
    überlappende Einträge, wird der erste (nach Standard-Sortierung) genügt, um
    die Person als abwesend zu erkennen.
    """
    return person.abwesenheiten.filter(von__lte=datum, bis__gte=datum).first()


def einteilen(person: Mitarbeiter, vorlage: Schichtvorlage, datum: date) -> Zuweisung:
    """Einen Mitarbeiter der Schicht ``vorlage`` am ``datum`` zuweisen — idempotent.

    Die konkrete Tagesschicht wird bei Bedarf angelegt (eine Vorlage wird erst
    durch das Einteilen an einem Tag zur planbaren Schicht). Eine bereits
    bestehende Zuweisung wird unverändert zurückgegeben, sodass mehrfaches
    Einteilen keine Doubletten erzeugt.

    Ist der Mitarbeiter am ``datum`` abwesend (Urlaub/Krank), wird die Einteilung
    mit ``EinteilenBlockiert`` abgelehnt — ein Abwesender darf nicht verplant
    werden.
    """
    abwesenheit = ist_abwesend(person, datum)
    if abwesenheit is not None:
        raise EinteilenBlockiert(
            f"{person.voller_name} ist am {datum:%d.%m.%Y} abwesend "
            f"({abwesenheit.art_anzeige}) und kann nicht eingeteilt werden."
        )
    schicht, _ = Schicht.objects.get_or_create(vorlage=vorlage, datum=datum)
    zuweisung, _ = Zuweisung.objects.get_or_create(schicht=schicht, mitarbeiter=person)
    return zuweisung


def abwesenheiten_je_woche(
    betrieb: Betrieb, tage: list[date]
) -> dict[tuple[int, date], Abwesenheit]:
    """Abwesenheiten der Woche je (Mitarbeiter, Tag) für die Gitter-Anzeige.

    Lädt alle Abwesenheiten, die das Wochenfenster überlappen, in einer einzigen
    Abfrage und ordnet sie den konkreten Tagen zu. So lässt sich im Gitter ohne
    N+1-Abfragen markieren, an welchen Tagen jemand nicht verfügbar ist.
    """
    treffer: dict[tuple[int, date], Abwesenheit] = {}
    abwesenheiten = Abwesenheit.objects.filter(
        mitarbeiter__betrieb=betrieb,
        von__lte=tage[-1],
        bis__gte=tage[0],
    )
    for abwesenheit in abwesenheiten:
        for tag in tage:
            if abwesenheit.umfasst(tag):
                treffer[(abwesenheit.mitarbeiter_id, tag)] = abwesenheit
    return treffer


def tageszuteilung(betrieb: Betrieb, person: Mitarbeiter, datum: date) -> dict:
    """Daten für die Einteilen-Seite eines Mitarbeiters an einem Tag.

    Liefert die bestehenden Zuweisungen dieses Tages sowie die Vorlagen, für die
    noch keine Zuweisung besteht (die also noch hinzugefügt werden können). So
    lässt sich jede Schicht je Tag höchstens einmal einteilen.
    """
    zuweisungen = list(
        Zuweisung.objects.filter(
            mitarbeiter=person,
            schicht__datum=datum,
            schicht__vorlage__betrieb=betrieb,
        ).select_related("schicht__vorlage")
    )
    belegte_vorlagen = {zuweisung.schicht.vorlage_id for zuweisung in zuweisungen}
    verfuegbar = betrieb.schichtvorlagen.exclude(id__in=belegte_vorlagen)
    return {"zuweisungen": zuweisungen, "verfuegbar": verfuegbar}
