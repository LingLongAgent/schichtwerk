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
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count

from . import regeln
from .models import (
    Abteilung,
    Abwesenheit,
    Betrieb,
    Mitarbeiter,
    Schicht,
    Schichtvorlage,
    Zuweisung,
)

STANDARD_BETRIEB_NAME = "Mein Betrieb"


class EinteilenBlockiert(Exception):
    """Eine Zuweisung ist fachlich nicht möglich (z. B. Abwesenheit am Tag).

    Wird von ``einteilen`` ausgelöst und in der View abgefangen, um dem Planer
    eine verständliche Meldung zu zeigen, statt eine ungültige Einteilung
    anzulegen.
    """

# Wochentags-Kürzel Mo–So für die Gitter-Kopfzeile (Index = date.weekday()).
WOCHENTAG_KUERZEL = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def aktueller_betrieb(user: object | None = None) -> Betrieb:
    """Liefert den Betrieb, in dessen Kontext gerade geplant wird.

    Seit M10 legt jedes Login bei der Registrierung seinen eigenen Betrieb an. Ist
    ein angemeldeter ``user`` mit einer ``Betriebszugehoerigkeit`` übergeben, wird
    dessen Betrieb verwendet. Ohne Zuordnung (oder ohne user) fällt die Funktion
    auf den zuerst angelegten Betrieb zurück — so bleiben Altzugänge und Tests, die
    keinen Account-Bezug haben, weiterhin nutzbar.

    Existiert noch gar kein Betrieb (frische Installation), wird ein
    Standard-Betrieb angelegt, damit die Ansichten nie ins Leere laufen.
    """
    if user is not None and getattr(user, "is_authenticated", False):
        # Lokaler Import: accounts hängt von planning.models ab, daher hier statt
        # auf Modulebene, um einen Import-Zyklus zu vermeiden.
        from accounts.models import Betriebszugehoerigkeit

        zugehoerigkeit = (
            Betriebszugehoerigkeit.objects.filter(user=user)
            .select_related("betrieb")
            .first()
        )
        if zugehoerigkeit is not None:
            return zugehoerigkeit.betrieb
    betrieb = Betrieb.objects.order_by("id").first()
    if betrieb is None:
        betrieb = Betrieb.objects.create(name=STANDARD_BETRIEB_NAME)
    return betrieb


def abteilung_filter(betrieb: Betrieb, roh: str | None) -> Abteilung | None:
    """Den Query-Parameter ``abteilung`` zu einer Abteilung des Betriebs auflösen.

    Fehlt der Parameter, ist er kein gültiger Wert oder verweist er auf eine
    fremde/unbekannte Abteilung, wird ``None`` zurückgegeben — der Plan zeigt dann
    alle Abteilungen. So führt eine manipulierte URL nie zu einem Fehler, sondern
    stets zur ungefilterten Ansicht.
    """
    if not roh:
        return None
    try:
        abteilung_id = int(roh)
    except (TypeError, ValueError):
        return None
    return betrieb.abteilungen.filter(pk=abteilung_id).first()


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


def wochengitter(
    betrieb: Betrieb, start: date, heute: date, abteilung: Abteilung | None = None
) -> dict:
    """Daten für das Wochengitter (Mitarbeiter × Wochentage) aufbereiten.

    Liefert je aktivem Mitarbeiter eine Zeile mit sieben Tageszellen; jede Zelle
    trägt die an diesem Tag zugewiesenen Schichten (nach Beginn sortiert). Alle
    Zuweisungen der Woche werden in einer einzigen Abfrage geladen und im
    Speicher den (Mitarbeiter, Tag)-Zellen zugeordnet, damit das Gitter keine
    N+1-Abfragen auslöst.

    Ist ``abteilung`` gesetzt (M8), wird der Plan darauf eingeschränkt: nur
    Mitarbeiter dieser Abteilung erscheinen als Zeilen und nur deren offene
    Schichten in der Offen-Spur. So lässt sich pro Standort/Bereich planen.

    Zusätzlich werden die Arbeitszeit-Regeln (M6) je Mitarbeiter ausgewertet:
    ``zeilen[i]["konflikte"]`` trägt die Verstöße der Zeile, ``konflikte`` eine
    nach Mitarbeitern gruppierte Übersicht und ``konflikt_schicht_ids`` die Menge
    der beteiligten Schichten, damit die Oberfläche die betroffenen Chips
    hervorheben kann.
    """
    tage = wochentage(start)
    aktive = betrieb.mitarbeiter.filter(aktiv=True)
    if abteilung is not None:
        aktive = aktive.filter(abteilung=abteilung)
    mitarbeiter = list(aktive)

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
    offen_je_tag = offene_schichten_je_tag(betrieb, tage, abteilung)
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
        "abteilung": abteilung,
    }


def offene_schichten_je_tag(
    betrieb: Betrieb, tage: list[date], abteilung: Abteilung | None = None
) -> dict[date, list[Schicht]]:
    """Unterbesetzte Schichten der Woche, je Tag und nach Beginn sortiert.

    „Offen" heißt: weniger Zuweisungen als ``bedarf`` — die Schicht braucht noch
    Personal. Die Zuweisungszahl wird per ``Count`` mitannotiert, damit der
    Offen-Status ohne eine Zusatzabfrage je Schicht (N+1) bestimmt werden kann.
    Nur Schichten des Betriebs im Wochenfenster werden betrachtet; ist
    ``abteilung`` gesetzt, zusätzlich nur deren Vorlagen.
    """
    schichten = (
        Schicht.objects.filter(vorlage__betrieb=betrieb, datum__range=(tage[0], tage[-1]))
        .select_related("vorlage")
        .annotate(anzahl_zuweisungen=Count("zuweisungen"))
    )
    if abteilung is not None:
        schichten = schichten.filter(vorlage__abteilung=abteilung)
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


def dashboard_daten(betrieb: Betrieb, start: date, heute: date) -> dict:
    """Kennzahlen und Auslastung der laufenden Woche für die Übersicht (M9).

    Die Übersicht soll einem Planer auf einen Blick zeigen, wie es um die Woche
    steht: vier Kennzahlen (aktive Mitarbeiter, geplante Schichten, noch offene
    Schichten, erkannte Konflikte), die geplanten Stunden je Mitarbeiter im
    Verhältnis zur Vertragszeit sowie die Besetzung je Wochentag.

    Alle Zuweisungen der Woche werden einmalig geladen und im Speicher zu Stunden
    je Mitarbeiter und Einteilungen je Tag verdichtet (kein N+1). Offene Schichten
    und Konflikte greifen auf die bereits bestehenden Bausteine (``offene_
    schichten_je_tag``, ``regeln.wochenkonflikte``) zurück, damit die Übersicht
    dieselbe Wahrheit zeigt wie der Dienstplan.
    """
    tage = wochentage(start)
    aktive = list(betrieb.mitarbeiter.filter(aktiv=True))

    stunden_je_person: dict[int, float] = defaultdict(float)
    eingeteilt_je_tag: dict[date, int] = defaultdict(int)
    zuweisungen = Zuweisung.objects.filter(
        mitarbeiter__betrieb=betrieb,
        schicht__datum__range=(tage[0], tage[-1]),
    ).select_related("schicht__vorlage")
    for zuweisung in zuweisungen:
        stunden_je_person[zuweisung.mitarbeiter_id] += zuweisung.schicht.dauer_stunden
        eingeteilt_je_tag[zuweisung.schicht.datum] += 1

    schichten_diese_woche = Schicht.objects.filter(
        vorlage__betrieb=betrieb, datum__range=(tage[0], tage[-1])
    ).count()

    offen_je_tag = offene_schichten_je_tag(betrieb, tage)
    offen_gesamt = sum(len(schichten) for schichten in offen_je_tag.values())

    konflikte_je_person = regeln.wochenkonflikte(betrieb, tage[0], tage[-1])
    konflikte_gesamt = sum(len(konflikte) for konflikte in konflikte_je_person.values())

    # Stunden je Mitarbeiter: geplante gegen vertraglich vereinbarte Zeit. Die
    # Auslastung treibt die Balkenbreite; über 100 % markiert Mehrarbeit.
    stunden_zeilen = []
    for person in aktive:
        geplant = stunden_je_person.get(person.id, 0.0)
        soll = float(person.vertragsstunden)
        auslastung = round(geplant / soll * 100) if soll else 0
        stunden_zeilen.append(
            {
                "person": person,
                "geplant": geplant,
                "soll": soll,
                "auslastung": auslastung,
                "balken": min(auslastung, 100),
                "ueberlastet": auslastung > 100,
            }
        )
    stunden_zeilen.sort(key=lambda zeile: zeile["geplant"], reverse=True)

    besetzung = [
        {
            "datum": tag,
            "kuerzel": WOCHENTAG_KUERZEL[index],
            "ist_heute": tag == heute,
            "eingeteilt": eingeteilt_je_tag.get(tag, 0),
            "offen": len(offen_je_tag.get(tag, [])),
        }
        for index, tag in enumerate(tage)
    ]

    kpis = [
        {"label": "Mitarbeiter", "value": len(aktive)},
        {"label": "Schichten diese Woche", "value": schichten_diese_woche},
        {"label": "Offene Schichten", "value": offen_gesamt},
        {"label": "Konflikte", "value": konflikte_gesamt},
    ]

    return {
        "start": start,
        "ende": tage[-1],
        "kpis": kpis,
        "stunden_zeilen": stunden_zeilen,
        "besetzung": besetzung,
        "hat_offene": offen_gesamt > 0,
        "hat_konflikte": konflikte_gesamt > 0,
    }


def stundenuebersicht(betrieb: Betrieb, start: date, heute: date) -> dict:
    """Geplante Stunden je Mitarbeiter über die Woche, gegen die Vertragszeit (M11).

    Ergänzt das Dashboard um eine vollständige Stunden-Tabelle: je aktivem
    Mitarbeiter die geplanten Stunden pro Wochentag (Mo–So), die Wochensumme und
    die Differenz zur vertraglich vereinbarten Zeit (positiv = Mehrarbeit,
    negativ = noch Luft). Zusätzlich die Tagessummen (Spaltensummen) und die
    Gesamtstunden der Woche, damit ein Planer Lastspitzen erkennt.

    Alle Zuweisungen der Woche werden in einer Abfrage geladen und im Speicher zu
    (Mitarbeiter, Tag)-Stunden verdichtet (kein N+1). Die reine Aufbereitung ist
    ohne HTTP testbar.
    """
    tage = wochentage(start)
    aktive = list(betrieb.mitarbeiter.filter(aktiv=True))

    stunden_je_zelle: dict[tuple[int, date], float] = defaultdict(float)
    zuweisungen = Zuweisung.objects.filter(
        mitarbeiter__betrieb=betrieb,
        schicht__datum__range=(tage[0], tage[-1]),
    ).select_related("schicht__vorlage")
    for zuweisung in zuweisungen:
        stunden_je_zelle[(zuweisung.mitarbeiter_id, zuweisung.schicht.datum)] += (
            zuweisung.schicht.dauer_stunden
        )

    zeilen = []
    tagessummen = [0.0] * len(tage)
    gesamt = 0.0
    for person in aktive:
        tagesstunden = [stunden_je_zelle.get((person.id, tag), 0.0) for tag in tage]
        summe = sum(tagesstunden)
        soll = float(person.vertragsstunden)
        zeilen.append(
            {
                "person": person,
                "tage": tagesstunden,
                "summe": summe,
                "soll": soll,
                "differenz": summe - soll,
            }
        )
        for index, stunden in enumerate(tagesstunden):
            tagessummen[index] += stunden
        gesamt += summe
    zeilen.sort(key=lambda zeile: zeile["summe"], reverse=True)

    kopf = [
        {
            "kuerzel": WOCHENTAG_KUERZEL[index],
            "datum": tag,
            "ist_heute": tag == heute,
            "ist_wochenende": index >= 5,
        }
        for index, tag in enumerate(tage)
    ]
    return {
        "start": start,
        "ende": tage[-1],
        "kopf": kopf,
        "zeilen": zeilen,
        "tagessummen": tagessummen,
        "gesamt": gesamt,
        "vorwoche": start - timedelta(days=7),
        "naechste": start + timedelta(days=7),
    }


# Spaltenüberschriften des Plan-Exports (CSV). Bewusst sprechend für den Empfänger.
PLAN_EXPORT_KOPF = [
    "Datum",
    "Wochentag",
    "Mitarbeiter",
    "Rolle",
    "Abteilung",
    "Schicht",
    "Beginn",
    "Ende",
    "Stunden",
]


def _stunden_dezimal(stunden: float) -> str:
    """Stunden als deutsche Dezimalzahl ohne überflüssige Nullen (z. B. ``7,5``)."""
    text = f"{stunden:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def plan_export_zeilen(betrieb: Betrieb, start: date) -> list[list[str]]:
    """Den Wochenplan als Tabellenzeilen für den CSV-Export aufbereiten (M11).

    Jede Zuweisung der Woche wird zu einer Zeile: Datum, Wochentag, Mitarbeiter,
    Rolle, Abteilung, Schichtname, Beginn/Ende und Stundenzahl. Sortiert nach
    Datum, dann Schichtbeginn, dann Mitarbeitername, damit der Export stabil und
    gut lesbar ist. Die Aufbereitung ist von der HTTP-/CSV-Schicht getrennt und
    damit isoliert testbar; alle Zuweisungen werden in einer Abfrage geladen.
    """
    tage = wochentage(start)
    zuweisungen = (
        Zuweisung.objects.filter(
            mitarbeiter__betrieb=betrieb,
            schicht__datum__range=(tage[0], tage[-1]),
        )
        .select_related("schicht__vorlage__abteilung", "mitarbeiter")
        .order_by("schicht__datum", "schicht__vorlage__beginn", "mitarbeiter__nachname")
    )
    zeilen: list[list[str]] = []
    for zuweisung in zuweisungen:
        schicht = zuweisung.schicht
        vorlage = schicht.vorlage
        person = zuweisung.mitarbeiter
        zeilen.append(
            [
                schicht.datum.isoformat(),
                WOCHENTAG_KUERZEL[schicht.datum.weekday()],
                person.voller_name,
                person.rolle,
                vorlage.abteilung.name if vorlage.abteilung else "",
                vorlage.name,
                f"{vorlage.beginn:%H:%M}",
                f"{vorlage.ende:%H:%M}",
                _stunden_dezimal(schicht.dauer_stunden),
            ]
        )
    return zeilen


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


@dataclass(frozen=True)
class OnboardingSchritt:
    """Ein geführter Einrichtungsschritt mit Ziel-Ansicht und Erledigt-Status."""

    schluessel: str
    titel: str
    beschreibung: str
    url_name: str
    erledigt: bool


@dataclass(frozen=True)
class OnboardingStatus:
    """Fortschritt der Ersteinrichtung eines frisch angelegten Betriebs."""

    schritte: list[OnboardingSchritt]

    @property
    def erledigt_anzahl(self) -> int:
        return sum(1 for schritt in self.schritte if schritt.erledigt)

    @property
    def gesamt(self) -> int:
        return len(self.schritte)

    @property
    def fertig(self) -> bool:
        """True, sobald alle Schritte erledigt sind (Onboarding abgeschlossen)."""
        return self.erledigt_anzahl == self.gesamt

    @property
    def naechster(self) -> OnboardingSchritt | None:
        """Der erste noch offene Schritt (für den Haupt-Aufruf), sonst ``None``."""
        return next((schritt for schritt in self.schritte if not schritt.erledigt), None)


def onboarding_status(betrieb: Betrieb) -> OnboardingStatus:
    """Den Einrichtungsfortschritt eines Betriebs als geführte Schrittliste bauen.

    Die drei Schritte spiegeln den kürzesten Weg zu einem nutzbaren Dienstplan:
    erst Mitarbeiter, dann eine Schichtvorlage, dann die erste Einteilung. Jeder
    Schritt gilt als erledigt, sobald der zugehörige Datenbestand existiert. Die
    Logik liest nur Zählwerte und ist damit ohne HTTP testbar.
    """
    hat_mitarbeiter = betrieb.mitarbeiter.exists()
    hat_vorlagen = betrieb.schichtvorlagen.exists()
    hat_zuweisung = Zuweisung.objects.filter(schicht__vorlage__betrieb=betrieb).exists()
    schritte = [
        OnboardingSchritt(
            schluessel="mitarbeiter",
            titel="Mitarbeiter anlegen",
            beschreibung="Lege die Personen an, die du verplanen möchtest.",
            url_name="planning:mitarbeiter_neu",
            erledigt=hat_mitarbeiter,
        ),
        OnboardingSchritt(
            schluessel="vorlagen",
            titel="Schichtvorlage anlegen",
            beschreibung="Definiere deine Dienste (z. B. Früh, Spät, Nacht) mit Zeiten.",
            url_name="planning:vorlage_neu",
            erledigt=hat_vorlagen,
        ),
        OnboardingSchritt(
            schluessel="einteilen",
            titel="Erste Schicht einteilen",
            beschreibung="Weise im Wochengitter einen Mitarbeiter einer Schicht zu.",
            url_name="planning:schedule",
            erledigt=hat_zuweisung,
        ),
    ]
    return OnboardingStatus(schritte=schritte)
