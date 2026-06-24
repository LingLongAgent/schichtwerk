"""``seed_demo`` — füllt eine frische Installation mit vorzeigbaren Beispieldaten.

Das Problem: Wer den Prototyp zum ersten Mal startet, sieht nur leere Listen und
kann das Wochengitter (den Kern) nicht beurteilen. Dieser Befehl legt einen
kompletten, plausiblen Demo-Betrieb an — Login, Abteilungen, Mitarbeiter,
Schichtvorlagen sowie eine bereits teilweise besetzte laufende Woche samt einer
Abwesenheit — sodass jede Ansicht sofort mit echten Daten gefüllt ist.

Der Befehl ist **idempotent**: Er bindet alle Objekte über natürliche Schlüssel
(Name/Benutzername) mit ``get_or_create`` ein, also kann er gefahrlos mehrfach
laufen, ohne Duplikate zu erzeugen. Bewusst bleiben einige Schichten unbesetzt,
damit „offene Schichten" und die Besetzungsanzeige etwas zu zeigen haben.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Betriebszugehoerigkeit
from planning.models import (
    Abteilung,
    Abwesenheit,
    Betrieb,
    Mitarbeiter,
    Schicht,
    Schichtvorlage,
    Zuweisung,
)

DEMO_BETRIEB = "Demo-Gastro GmbH"
DEMO_LOGIN = "demo"
DEMO_PASSWORT = "demo12345"


@dataclass(frozen=True)
class _MitarbeiterVorlage:
    """Bauplan eines Demo-Mitarbeiters (Abteilung als Name, später aufgelöst)."""

    vorname: str
    nachname: str
    rolle: str
    abteilung: str
    vertragsstunden: int
    farbe: str


@dataclass(frozen=True)
class _SchichtVorlage:
    """Bauplan einer Demo-Schichtvorlage."""

    name: str
    beginn: time
    ende: time
    abteilung: str
    rolle: str
    farbe: str
    bedarf: int


ABTEILUNGEN = ["Küche", "Service", "Empfang"]

MITARBEITER = [
    _MitarbeiterVorlage("Anna", "Becker", "Köchin", "Küche", 40, "#2563eb"),
    _MitarbeiterVorlage("Bekir", "Yilmaz", "Beikoch", "Küche", 30, "#16a34a"),
    _MitarbeiterVorlage("Clara", "Schmidt", "Servicekraft", "Service", 40, "#db2777"),
    _MitarbeiterVorlage("David", "Wagner", "Servicekraft", "Service", 20, "#d97706"),
    _MitarbeiterVorlage("Elif", "Demir", "Empfang", "Empfang", 40, "#7c3aed"),
    _MitarbeiterVorlage("Felix", "Hofmann", "Aushilfe", "Service", 15, "#0891b2"),
]

SCHICHTVORLAGEN = [
    _SchichtVorlage("Frühschicht", time(6, 0), time(14, 0), "Küche", "Köchin", "#2563eb", 2),
    _SchichtVorlage("Spätschicht", time(14, 0), time(22, 0), "Service", "Servicekraft", "#db2777", 2),
    _SchichtVorlage("Empfang", time(8, 0), time(16, 0), "Empfang", "Empfang", "#7c3aed", 1),
    _SchichtVorlage("Nachtdienst", time(22, 0), time(6, 0), "Service", "", "#475569", 1),
]


class Command(BaseCommand):
    help = "Legt einen vollständigen Demo-Betrieb mit Beispieldaten an (idempotent)."

    def handle(self, *args: object, **options: object) -> None:
        with transaction.atomic():
            betrieb = self._betrieb_und_login()
            abteilungen = self._abteilungen(betrieb)
            mitarbeiter = self._mitarbeiter(betrieb, abteilungen)
            vorlagen = self._vorlagen(betrieb, abteilungen)
            self._wochenplan(vorlagen, mitarbeiter)
            self._abwesenheit(mitarbeiter)
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo-Daten bereit. Login: {DEMO_LOGIN} / {DEMO_PASSWORT}"
            )
        )

    def _betrieb_und_login(self) -> Betrieb:
        """Demo-Betrieb und zugehöriges Login anlegen (beide idempotent)."""
        betrieb, _ = Betrieb.objects.get_or_create(name=DEMO_BETRIEB)
        user_model = get_user_model()
        user, neu = user_model.objects.get_or_create(username=DEMO_LOGIN)
        if neu:
            user.set_password(DEMO_PASSWORT)
            user.save(update_fields=["password"])
        Betriebszugehoerigkeit.objects.get_or_create(
            user=user, defaults={"betrieb": betrieb}
        )
        return betrieb

    def _abteilungen(self, betrieb: Betrieb) -> dict[str, Abteilung]:
        abteilungen: dict[str, Abteilung] = {}
        for name in ABTEILUNGEN:
            abteilung, _ = Abteilung.objects.get_or_create(betrieb=betrieb, name=name)
            abteilungen[name] = abteilung
        return abteilungen

    def _mitarbeiter(
        self, betrieb: Betrieb, abteilungen: dict[str, Abteilung]
    ) -> list[Mitarbeiter]:
        personen: list[Mitarbeiter] = []
        for vorlage in MITARBEITER:
            person, _ = Mitarbeiter.objects.get_or_create(
                betrieb=betrieb,
                vorname=vorlage.vorname,
                nachname=vorlage.nachname,
                defaults={
                    "rolle": vorlage.rolle,
                    "abteilung": abteilungen[vorlage.abteilung],
                    "vertragsstunden": Decimal(vorlage.vertragsstunden),
                    "farbe": vorlage.farbe,
                },
            )
            personen.append(person)
        return personen

    def _vorlagen(
        self, betrieb: Betrieb, abteilungen: dict[str, Abteilung]
    ) -> list[Schichtvorlage]:
        vorlagen: list[Schichtvorlage] = []
        for bauplan in SCHICHTVORLAGEN:
            vorlage, _ = Schichtvorlage.objects.get_or_create(
                betrieb=betrieb,
                name=bauplan.name,
                defaults={
                    "beginn": bauplan.beginn,
                    "ende": bauplan.ende,
                    "abteilung": abteilungen[bauplan.abteilung],
                    "benoetigte_rolle": bauplan.rolle,
                    "farbe": bauplan.farbe,
                },
            )
            vorlagen.append(vorlage)
        return vorlagen

    def _wochenplan(
        self, vorlagen: list[Schichtvorlage], mitarbeiter: list[Mitarbeiter]
    ) -> None:
        """Die laufende Woche mit Schichten füllen und teilweise besetzen.

        Pro Werktag (Mo–Fr) jede Vorlage als Schicht anlegen und nach einem festen
        Muster besetzen — bewusst unvollständig, damit „offene Schichten"
        sichtbar bleiben. Das Muster ist deterministisch (Index-basiert), also
        bei wiederholtem Lauf stabil.
        """
        montag = _wochenmontag()
        for bauplan, vorlage in zip(SCHICHTVORLAGEN, vorlagen, strict=True):
            for tag_versatz in range(5):  # Mo–Fr
                tag = montag + timedelta(days=tag_versatz)
                schicht, _ = Schicht.objects.get_or_create(
                    vorlage=vorlage, datum=tag, defaults={"bedarf": bauplan.bedarf}
                )
                self._besetze(schicht, vorlage, mitarbeiter, tag_versatz)

    def _besetze(
        self,
        schicht: Schicht,
        vorlage: Schichtvorlage,
        mitarbeiter: list[Mitarbeiter],
        tag_versatz: int,
    ) -> None:
        """Eine Schicht passend zur Abteilung der Vorlage teilweise besetzen.

        Es wird genau ein Mitarbeiter der passenden Abteilung zugewiesen (rotierend
        über die Woche), sodass mehrfach besetzte Schichten (Bedarf 2) bewusst
        unterbesetzt — also „offen" — bleiben.
        """
        passende = [
            person
            for person in mitarbeiter
            if person.abteilung_id == vorlage.abteilung_id
        ]
        if not passende:
            return
        person = passende[tag_versatz % len(passende)]
        Zuweisung.objects.get_or_create(schicht=schicht, mitarbeiter=person)

    def _abwesenheit(self, mitarbeiter: list[Mitarbeiter]) -> None:
        """Dem ersten Mitarbeiter einen Urlaub in der laufenden Woche eintragen."""
        if not mitarbeiter:
            return
        montag = _wochenmontag()
        Abwesenheit.objects.get_or_create(
            mitarbeiter=mitarbeiter[0],
            von=montag,
            bis=montag + timedelta(days=2),
            defaults={"art": Abwesenheit.URLAUB, "notiz": "Demo-Urlaub"},
        )


def _wochenmontag(heute: date | None = None) -> date:
    """Montag der Woche, die ``heute`` (Default: aktuelles Datum) enthält."""
    heute = heute or date.today()
    return heute - timedelta(days=heute.weekday())
