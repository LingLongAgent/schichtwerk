"""Tests für den ``seed_demo``-Management-Befehl.

Geprüft wird, dass der Befehl einen vollständigen, anmeldbaren Demo-Betrieb
erzeugt und — als zentrale Eigenschaft — **idempotent** ist: Ein zweiter Lauf
darf keine Duplikate anlegen. Außerdem soll bewusst mindestens eine offene
Schicht übrig bleiben, damit die Besetzungsanzeige etwas zu zeigen hat.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.test import TestCase

from accounts.models import Betriebszugehoerigkeit
from planning.management.commands.seed_demo import (
    DEMO_BETRIEB,
    DEMO_LOGIN,
    DEMO_PASSWORT,
)
from planning.models import (
    Abteilung,
    Abwesenheit,
    Betrieb,
    Mitarbeiter,
    Schicht,
    Schichtvorlage,
    Zuweisung,
)


class SeedDemoTests(TestCase):
    def _seed(self) -> None:
        call_command("seed_demo", stdout=StringIO())

    def test_legt_betrieb_und_anmeldbares_login_an(self) -> None:
        self._seed()

        self.assertTrue(Betrieb.objects.filter(name=DEMO_BETRIEB).exists())
        user = get_user_model().objects.get(username=DEMO_LOGIN)
        self.assertIsNotNone(
            authenticate(username=DEMO_LOGIN, password=DEMO_PASSWORT)
        )
        zugehoerigkeit = Betriebszugehoerigkeit.objects.get(user=user)
        self.assertEqual(zugehoerigkeit.betrieb.name, DEMO_BETRIEB)

    def test_erzeugt_vollstaendigen_datengraphen(self) -> None:
        self._seed()

        betrieb = Betrieb.objects.get(name=DEMO_BETRIEB)
        self.assertEqual(Abteilung.objects.filter(betrieb=betrieb).count(), 3)
        self.assertEqual(Mitarbeiter.objects.filter(betrieb=betrieb).count(), 6)
        self.assertEqual(Schichtvorlage.objects.filter(betrieb=betrieb).count(), 4)
        # Mo–Fr × 4 Vorlagen = 20 Schichten in der laufenden Woche.
        self.assertEqual(Schicht.objects.count(), 20)
        self.assertTrue(Zuweisung.objects.exists())
        self.assertTrue(Abwesenheit.objects.exists())

    def test_laesst_offene_schichten_uebrig(self) -> None:
        self._seed()

        offene = [schicht for schicht in Schicht.objects.all() if schicht.ist_offen]
        self.assertTrue(offene, "Es sollten bewusst offene Schichten verbleiben.")

    def test_ist_idempotent(self) -> None:
        self._seed()
        self._seed()

        self.assertEqual(Betrieb.objects.filter(name=DEMO_BETRIEB).count(), 1)
        self.assertEqual(get_user_model().objects.filter(username=DEMO_LOGIN).count(), 1)
        self.assertEqual(Mitarbeiter.objects.count(), 6)
        self.assertEqual(Schichtvorlage.objects.count(), 4)
        self.assertEqual(Schicht.objects.count(), 20)
        self.assertEqual(Betriebszugehoerigkeit.objects.count(), 1)
