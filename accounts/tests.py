"""Tests für Registrierung und Mandantenzuordnung (M10).

M10 öffnet den Prototyp für mehrere Betriebe: Bei der Registrierung entstehen in
einem Schritt ein Login und ein eigener Betrieb, beide werden über eine
``Betriebszugehoerigkeit`` verbunden. Geprüft werden drei Ebenen: das Formular
(legt User + Betrieb + Zuordnung an, weist ungültige Eingaben ab), die View
(GET/POST, Anmeldung, Weiterleitung, kein Zugang für bereits Angemeldete) und die
Auflösung ``aktueller_betrieb``, die nun den Betrieb des angemeldeten Nutzers
bevorzugt und ohne Zuordnung wie bisher auf den ersten Betrieb zurückfällt.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from planning import services
from planning.factories import BetriebFactory
from planning.models import Betrieb

from .forms import RegistrierungForm
from .models import Betriebszugehoerigkeit

User = get_user_model()

GUELTIGE_DATEN = {
    "betrieb_name": "Bäckerei Sonnenschein",
    "username": "chefin",
    "email": "chefin@example.com",
    "password1": "Brioche!2026",
    "password2": "Brioche!2026",
}


class RegistrierungFormTests(TestCase):
    """Das Formular legt Login, Betrieb und ihre Zuordnung gebündelt an."""

    def test_legt_user_betrieb_und_zuordnung_an(self) -> None:
        form = RegistrierungForm(data=GUELTIGE_DATEN)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.username, "chefin")
        self.assertEqual(user.email, "chefin@example.com")
        betrieb = Betrieb.objects.get(name="Bäckerei Sonnenschein")
        self.assertEqual(user.zugehoerigkeit.betrieb, betrieb)

    def test_email_ist_optional(self) -> None:
        daten = {**GUELTIGE_DATEN, "email": ""}
        form = RegistrierungForm(data=daten)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, "")

    def test_passwort_muss_uebereinstimmen(self) -> None:
        daten = {**GUELTIGE_DATEN, "password2": "Anderes!2026"}
        form = RegistrierungForm(data=daten)
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_betrieb_name_ist_pflicht(self) -> None:
        daten = {**GUELTIGE_DATEN, "betrieb_name": ""}
        form = RegistrierungForm(data=daten)
        self.assertFalse(form.is_valid())
        self.assertIn("betrieb_name", form.errors)

    def test_doppelter_username_abgewiesen(self) -> None:
        User.objects.create_user("chefin", password="x")
        form = RegistrierungForm(data=GUELTIGE_DATEN)
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_ungueltige_eingabe_legt_nichts_an(self) -> None:
        daten = {**GUELTIGE_DATEN, "password2": "Anderes!2026"}
        form = RegistrierungForm(data=daten)
        self.assertFalse(form.is_valid())
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Betrieb.objects.count(), 0)


class RegistrierungViewTests(TestCase):
    """Die View rendert das Formular, meldet an und leitet ins Onboarding."""

    def test_get_zeigt_formular(self) -> None:
        antwort = self.client.get(reverse("registrieren"))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Betrieb registrieren")

    def test_post_legt_an_meldet_an_und_leitet_ins_onboarding(self) -> None:
        antwort = self.client.post(reverse("registrieren"), GUELTIGE_DATEN)
        self.assertRedirects(antwort, reverse("planning:onboarding"))
        self.assertTrue(Betriebszugehoerigkeit.objects.filter(user__username="chefin").exists())
        # Nach erfolgreicher Registrierung ist der Nutzer angemeldet.
        self.assertIn("_auth_user_id", self.client.session)

    def test_ungueltiger_post_zeigt_formular_erneut(self) -> None:
        daten = {**GUELTIGE_DATEN, "password2": "Anderes!2026"}
        antwort = self.client.post(reverse("registrieren"), daten)
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(User.objects.count(), 0)

    def test_angemeldeter_nutzer_wird_umgeleitet(self) -> None:
        User.objects.create_user("schon_da", password="Brioche!2026")
        self.client.login(username="schon_da", password="Brioche!2026")
        antwort = self.client.get(reverse("registrieren"))
        self.assertRedirects(antwort, reverse("dashboard"))


class AktuellerBetriebTests(TestCase):
    """``aktueller_betrieb`` bevorzugt den Betrieb des angemeldeten Nutzers."""

    def test_nutzer_mit_zuordnung_erhaelt_eigenen_betrieb(self) -> None:
        erster = BetriebFactory()  # älter (kleinere id) — der bisherige Fallback
        eigener = BetriebFactory()
        user = User.objects.create_user("planer", password="x")
        Betriebszugehoerigkeit.objects.create(user=user, betrieb=eigener)
        self.assertNotEqual(erster.pk, eigener.pk)
        self.assertEqual(services.aktueller_betrieb(user), eigener)

    def test_nutzer_ohne_zuordnung_faellt_auf_ersten_betrieb_zurueck(self) -> None:
        erster = BetriebFactory()
        BetriebFactory()
        user = User.objects.create_user("ohne", password="x")
        self.assertEqual(services.aktueller_betrieb(user), erster)

    def test_ohne_user_unveraendert_erster_betrieb(self) -> None:
        erster = BetriebFactory()
        BetriebFactory()
        self.assertEqual(services.aktueller_betrieb(), erster)

    def test_leere_installation_legt_standardbetrieb_an(self) -> None:
        self.assertEqual(Betrieb.objects.count(), 0)
        betrieb = services.aktueller_betrieb()
        self.assertEqual(betrieb.name, services.STANDARD_BETRIEB_NAME)
