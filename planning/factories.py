"""factory_boy-Fabriken für realistische Testdaten.

Zentralisiert das Anlegen valider Objektgraphen, damit Tests sich auf das zu
prüfende Verhalten konzentrieren statt auf Boilerplate. Beziehungen sind über
``SubFactory`` verdrahtet, sodass z. B. eine ``SchichtFactory`` automatisch
einen Betrieb samt Vorlage erzeugt.
"""

from __future__ import annotations

from datetime import date, time

import factory
from factory.django import DjangoModelFactory

from .models import (
    Abteilung,
    Abwesenheit,
    Betrieb,
    Mitarbeiter,
    Schicht,
    Schichtvorlage,
    Zuweisung,
)


class BetriebFactory(DjangoModelFactory):
    class Meta:
        model = Betrieb

    name = factory.Sequence(lambda n: f"Betrieb {n}")


class AbteilungFactory(DjangoModelFactory):
    class Meta:
        model = Abteilung

    betrieb = factory.SubFactory(BetriebFactory)
    name = factory.Sequence(lambda n: f"Abteilung {n}")


class MitarbeiterFactory(DjangoModelFactory):
    class Meta:
        model = Mitarbeiter

    betrieb = factory.SubFactory(BetriebFactory)
    vorname = factory.Faker("first_name", locale="de_DE")
    nachname = factory.Faker("last_name", locale="de_DE")
    rolle = "Fachkraft"
    vertragsstunden = 40
    farbe = "#2563eb"
    aktiv = True


class SchichtvorlageFactory(DjangoModelFactory):
    class Meta:
        model = Schichtvorlage

    betrieb = factory.SubFactory(BetriebFactory)
    name = factory.Sequence(lambda n: f"Schicht {n}")
    beginn = time(6, 0)
    ende = time(14, 0)


class SchichtFactory(DjangoModelFactory):
    class Meta:
        model = Schicht

    vorlage = factory.SubFactory(SchichtvorlageFactory)
    datum = factory.Faker("date_object")
    bedarf = 1


class ZuweisungFactory(DjangoModelFactory):
    class Meta:
        model = Zuweisung

    schicht = factory.SubFactory(SchichtFactory)
    mitarbeiter = factory.SubFactory(MitarbeiterFactory)


class AbwesenheitFactory(DjangoModelFactory):
    class Meta:
        model = Abwesenheit

    mitarbeiter = factory.SubFactory(MitarbeiterFactory)
    art = Abwesenheit.URLAUB
    von = date(2026, 6, 22)
    bis = date(2026, 6, 26)
