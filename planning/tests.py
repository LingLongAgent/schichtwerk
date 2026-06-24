"""Tests für das Datenmodell (M1).

Geprüft werden die fachlich tragenden Eigenschaften: Schichtdauer inkl.
Nachtschichten über Mitternacht, der Offen-Status einer Schicht in Abhängigkeit
vom Bedarf sowie die Eindeutigkeits-Constraints, die Doppeldaten verhindern.
Reine Logik (Stundenberechnung) wird gründlich mit Randfällen abgedeckt.
"""

from __future__ import annotations

from datetime import date, time

from django.db import IntegrityError
from django.test import TestCase

from .factories import (
    AbteilungFactory,
    BetriebFactory,
    MitarbeiterFactory,
    SchichtFactory,
    SchichtvorlageFactory,
    ZuweisungFactory,
)
from .models import Schichtvorlage, Zuweisung, _stunden_zwischen


class StundenLogikTests(TestCase):
    """Reine Zeit-Logik — der Baustein für spätere Stunden- und Ruhezeitregeln."""

    def test_normale_tagschicht(self) -> None:
        self.assertEqual(_stunden_zwischen(time(6, 0), time(14, 0)), 8.0)

    def test_nachtschicht_ueber_mitternacht(self) -> None:
        # 22:00–06:00 ergibt 8 Stunden, obwohl das Ende kalendarisch "kleiner" ist.
        self.assertEqual(_stunden_zwischen(time(22, 0), time(6, 0)), 8.0)

    def test_halbe_stunde(self) -> None:
        self.assertEqual(_stunden_zwischen(time(8, 0), time(16, 30)), 8.5)

    def test_gleicher_zeitpunkt_ist_voller_tag(self) -> None:
        # Beginn == Ende interpretieren wir als 24-Stunden-Dienst, nicht als 0.
        self.assertEqual(_stunden_zwischen(time(8, 0), time(8, 0)), 24.0)


class SchichtvorlageTests(TestCase):
    def test_dauer_stunden_nutzt_zeitlogik(self) -> None:
        vorlage = SchichtvorlageFactory(beginn=time(14, 0), ende=time(22, 0))
        self.assertEqual(vorlage.dauer_stunden, 8.0)

    def test_str_zeigt_name_und_zeiten(self) -> None:
        vorlage = SchichtvorlageFactory(name="Früh", beginn=time(6, 0), ende=time(14, 0))
        self.assertEqual(str(vorlage), "Früh (06:00–14:00)")


class MitarbeiterTests(TestCase):
    def test_voller_name(self) -> None:
        person = MitarbeiterFactory(vorname="Anna", nachname="Berg")
        self.assertEqual(person.voller_name, "Anna Berg")


class SchichtTests(TestCase):
    def test_schicht_ohne_zuweisung_ist_offen(self) -> None:
        schicht = SchichtFactory(bedarf=1)
        self.assertTrue(schicht.ist_offen)
        self.assertEqual(schicht.anzahl_zugewiesen, 0)

    def test_schicht_mit_genug_zuweisungen_ist_besetzt(self) -> None:
        schicht = SchichtFactory(bedarf=1)
        ZuweisungFactory(schicht=schicht)
        self.assertFalse(schicht.ist_offen)
        self.assertEqual(schicht.anzahl_zugewiesen, 1)

    def test_schicht_bleibt_offen_bis_bedarf_gedeckt(self) -> None:
        schicht = SchichtFactory(bedarf=2)
        ZuweisungFactory(schicht=schicht)
        self.assertTrue(schicht.ist_offen)

    def test_betrieb_wird_aus_vorlage_abgeleitet(self) -> None:
        betrieb = BetriebFactory()
        vorlage = SchichtvorlageFactory(betrieb=betrieb)
        schicht = SchichtFactory(vorlage=vorlage)
        self.assertEqual(schicht.betrieb, betrieb)

    def test_eine_schicht_je_vorlage_und_datum(self) -> None:
        vorlage = SchichtvorlageFactory()
        SchichtFactory(vorlage=vorlage, datum=date(2026, 6, 24))
        with self.assertRaises(IntegrityError):
            SchichtFactory(vorlage=vorlage, datum=date(2026, 6, 24))


class ZuweisungTests(TestCase):
    def test_mitarbeiter_nur_einmal_pro_schicht(self) -> None:
        schicht = SchichtFactory()
        person = MitarbeiterFactory()
        ZuweisungFactory(schicht=schicht, mitarbeiter=person)
        with self.assertRaises(IntegrityError):
            Zuweisung.objects.create(schicht=schicht, mitarbeiter=person)


class AbteilungTests(TestCase):
    def test_abteilungsname_je_betrieb_eindeutig(self) -> None:
        betrieb = BetriebFactory()
        AbteilungFactory(betrieb=betrieb, name="Küche")
        with self.assertRaises(IntegrityError):
            AbteilungFactory(betrieb=betrieb, name="Küche")

    def test_gleicher_name_in_anderem_betrieb_erlaubt(self) -> None:
        AbteilungFactory(betrieb=BetriebFactory(), name="Küche")
        AbteilungFactory(betrieb=BetriebFactory(), name="Küche")
        self.assertEqual(Schichtvorlage.objects.count(), 0)  # kein Seiteneffekt
