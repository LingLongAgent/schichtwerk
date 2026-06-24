"""Tests für die Mitarbeiterverwaltung (M2).

Geprüft werden das Formular (Mandanten-Begrenzung der Abteilungen, Setzen des
Betriebs beim Speichern) und die Views (Liste, Detail, Anlegen, Bearbeiten)
inklusive Login-Schutz und der korrekten Zuordnung zum aktiven Betrieb.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .factories import AbteilungFactory, BetriebFactory, MitarbeiterFactory
from .forms import MitarbeiterForm
from .models import Mitarbeiter


class MitarbeiterFormTests(TestCase):
    """Das Formular kapselt Mandanten-Regeln, die die Views absichern."""

    def test_abteilungsauswahl_nur_aus_eigenem_betrieb(self) -> None:
        betrieb = BetriebFactory()
        eigene = AbteilungFactory(betrieb=betrieb, name="Küche")
        fremde = AbteilungFactory(betrieb=BetriebFactory(), name="Empfang")
        form = MitarbeiterForm(betrieb=betrieb)
        auswahl = list(form.fields["abteilung"].queryset)
        self.assertIn(eigene, auswahl)
        self.assertNotIn(fremde, auswahl)

    def test_save_setzt_betrieb(self) -> None:
        betrieb = BetriebFactory()
        form = MitarbeiterForm(
            data={"vorname": "Anna", "nachname": "Berg", "vertragsstunden": "40", "farbe": "#2563eb"},
            betrieb=betrieb,
        )
        self.assertTrue(form.is_valid(), form.errors)
        person = form.save()
        self.assertEqual(person.betrieb, betrieb)

    def test_pflichtfelder_fehlen_ist_ungueltig(self) -> None:
        form = MitarbeiterForm(data={"vorname": "", "nachname": ""}, betrieb=BetriebFactory())
        self.assertFalse(form.is_valid())
        self.assertIn("vorname", form.errors)
        self.assertIn("nachname", form.errors)


class MitarbeiterViewTests(TestCase):
    """Die Views arbeiten gegen den aktiven (ersten) Betrieb."""

    def setUp(self) -> None:
        # Name sortiert vor allen Zweit-Betrieben, damit aktueller_betrieb()
        # (Betrieb.objects.first(), Sortierung nach Name) deterministisch diesen wählt.
        self.betrieb = BetriebFactory(name="Aktiv-Betrieb")
        self.user = get_user_model().objects.create_user("planer", password="geheim123")
        self.client.force_login(self.user)

    def test_liste_zeigt_eigene_mitarbeiter(self) -> None:
        person = MitarbeiterFactory(betrieb=self.betrieb, vorname="Lea", nachname="Funk")
        antwort = self.client.get(reverse("planning:mitarbeiter_liste"))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Lea Funk")
        self.assertEqual(list(antwort.context["mitarbeiter_liste"]), [person])

    def test_liste_zeigt_keine_fremden_mitarbeiter(self) -> None:
        MitarbeiterFactory(betrieb=BetriebFactory(name="Zweit-Betrieb"), vorname="Fremd", nachname="Person")
        antwort = self.client.get(reverse("planning:mitarbeiter_liste"))
        self.assertNotContains(antwort, "Fremd Person")

    def test_anlegen_erstellt_mitarbeiter_im_betrieb(self) -> None:
        antwort = self.client.post(
            reverse("planning:mitarbeiter_neu"),
            {"vorname": "Max", "nachname": "Klein", "rolle": "Fachkraft",
             "vertragsstunden": "32", "farbe": "#10b981"},
        )
        person = Mitarbeiter.objects.get(vorname="Max", nachname="Klein")
        self.assertEqual(person.betrieb, self.betrieb)
        self.assertRedirects(antwort, reverse("planning:mitarbeiter_detail", args=[person.pk]))

    def test_bearbeiten_aendert_daten(self) -> None:
        person = MitarbeiterFactory(betrieb=self.betrieb, rolle="Aushilfe")
        self.client.post(
            reverse("planning:mitarbeiter_bearbeiten", args=[person.pk]),
            {"vorname": person.vorname, "nachname": person.nachname, "rolle": "Schichtleitung",
             "vertragsstunden": "40", "farbe": "#2563eb"},
        )
        person.refresh_from_db()
        self.assertEqual(person.rolle, "Schichtleitung")

    def test_detail_fuer_fremden_mitarbeiter_ist_404(self) -> None:
        fremd = MitarbeiterFactory(betrieb=BetriebFactory(name="Zweit-Betrieb"))
        antwort = self.client.get(reverse("planning:mitarbeiter_detail", args=[fremd.pk]))
        self.assertEqual(antwort.status_code, 404)

    def test_login_erforderlich(self) -> None:
        self.client.logout()
        antwort = self.client.get(reverse("planning:mitarbeiter_liste"))
        self.assertEqual(antwort.status_code, 302)
        self.assertIn("/konto/anmelden/", antwort["Location"])
