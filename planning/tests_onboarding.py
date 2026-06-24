"""Tests für das geführte Onboarding (M10).

Direkt nach der Registrierung führt das Onboarding den frischen Betrieb in drei
Schritten zum ersten Dienstplan: Mitarbeiter anlegen, Schichtvorlage anlegen,
erste Schicht einteilen. Geprüft werden die reine Status-Logik
(``services.onboarding_status``: welcher Schritt gilt wann als erledigt, wann ist
das Onboarding fertig) und die View (Login-Schutz, korrekte Darstellung von
offenem und abgeschlossenem Zustand).

Der 22.06.2026 ist ein Montag.
"""

from __future__ import annotations

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .factories import (
    BetriebFactory,
    MitarbeiterFactory,
    SchichtFactory,
    SchichtvorlageFactory,
    ZuweisungFactory,
)

User = get_user_model()
MONTAG = date(2026, 6, 22)


class OnboardingStatusTests(TestCase):
    """Die reine Status-Logik: Schritte, Erledigt-Stand, Fertig-Flag."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()

    def test_frischer_betrieb_hat_drei_offene_schritte(self) -> None:
        status = services.onboarding_status(self.betrieb)
        self.assertEqual(status.gesamt, 3)
        self.assertEqual(status.erledigt_anzahl, 0)
        self.assertFalse(status.fertig)
        self.assertFalse(any(schritt.erledigt for schritt in status.schritte))

    def test_naechster_schritt_ist_mitarbeiter(self) -> None:
        status = services.onboarding_status(self.betrieb)
        self.assertEqual(status.naechster.schluessel, "mitarbeiter")

    def test_mitarbeiter_erledigt_ersten_schritt(self) -> None:
        MitarbeiterFactory(betrieb=self.betrieb)
        status = services.onboarding_status(self.betrieb)
        schritt = {s.schluessel: s for s in status.schritte}["mitarbeiter"]
        self.assertTrue(schritt.erledigt)
        self.assertEqual(status.erledigt_anzahl, 1)
        self.assertEqual(status.naechster.schluessel, "vorlagen")

    def test_vorlage_erledigt_zweiten_schritt(self) -> None:
        SchichtvorlageFactory(betrieb=self.betrieb)
        status = services.onboarding_status(self.betrieb)
        schritt = {s.schluessel: s for s in status.schritte}["vorlagen"]
        self.assertTrue(schritt.erledigt)

    def test_zuweisung_erledigt_dritten_schritt(self) -> None:
        person = MitarbeiterFactory(betrieb=self.betrieb)
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(6), ende=time(14))
        schicht = SchichtFactory(vorlage=vorlage, datum=MONTAG)
        ZuweisungFactory(schicht=schicht, mitarbeiter=person)
        status = services.onboarding_status(self.betrieb)
        self.assertTrue(status.fertig)
        self.assertEqual(status.erledigt_anzahl, 3)
        self.assertIsNone(status.naechster)

    def test_status_ist_auf_betrieb_gescoped(self) -> None:
        # Daten eines anderen Betriebs zählen nicht für diesen.
        MitarbeiterFactory()
        status = services.onboarding_status(self.betrieb)
        self.assertEqual(status.erledigt_anzahl, 0)


class OnboardingViewTests(TestCase):
    """Die Onboarding-Seite: Login-Schutz und Darstellung der Zustände."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.user = User.objects.create_user("planer", password="geheim123!")
        self.client.login(username="planer", password="geheim123!")

    def test_login_noetig(self) -> None:
        self.client.logout()
        antwort = self.client.get(reverse("planning:onboarding"))
        self.assertEqual(antwort.status_code, 302)
        self.assertIn(reverse("login"), antwort.url)

    def test_offenes_onboarding_zeigt_schritte(self) -> None:
        antwort = self.client.get(reverse("planning:onboarding"))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Mitarbeiter anlegen")
        self.assertContains(antwort, "0 von 3 erledigt")

    def test_fertiges_onboarding_zeigt_abschluss(self) -> None:
        person = MitarbeiterFactory(betrieb=self.betrieb)
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(6), ende=time(14))
        schicht = SchichtFactory(vorlage=vorlage, datum=MONTAG)
        ZuweisungFactory(schicht=schicht, mitarbeiter=person)
        antwort = self.client.get(reverse("planning:onboarding"))
        self.assertContains(antwort, "Alles eingerichtet")
