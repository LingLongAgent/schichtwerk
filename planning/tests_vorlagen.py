"""Tests für die Schichtvorlagen-Verwaltung (M3).

Geprüft werden das Formular (Mandanten-Begrenzung der Abteilungen, Setzen des
Betriebs, die Sonderregel rund um Beginn/Ende inkl. erlaubter Nachtschicht) und
die Views (Liste, Detail, Anlegen, Bearbeiten, Löschen) inklusive Login-Schutz
und korrekter Zuordnung zum aktiven Betrieb.
"""

from __future__ import annotations

from datetime import time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .factories import AbteilungFactory, BetriebFactory, SchichtvorlageFactory
from .forms import SchichtvorlageForm
from .models import Schichtvorlage


class SchichtvorlageFormTests(TestCase):
    """Das Formular kapselt Mandanten- und Zeitregeln, die die Views absichern."""

    def test_abteilungsauswahl_nur_aus_eigenem_betrieb(self) -> None:
        betrieb = BetriebFactory()
        eigene = AbteilungFactory(betrieb=betrieb, name="Küche")
        fremde = AbteilungFactory(betrieb=BetriebFactory(), name="Empfang")
        form = SchichtvorlageForm(betrieb=betrieb)
        auswahl = list(form.fields["abteilung"].queryset)
        self.assertIn(eigene, auswahl)
        self.assertNotIn(fremde, auswahl)

    def test_save_setzt_betrieb(self) -> None:
        betrieb = BetriebFactory()
        form = SchichtvorlageForm(
            data={"name": "Frühschicht", "beginn": "06:00", "ende": "14:00", "farbe": "#2563eb"},
            betrieb=betrieb,
        )
        self.assertTrue(form.is_valid(), form.errors)
        vorlage = form.save()
        self.assertEqual(vorlage.betrieb, betrieb)

    def test_nachtschicht_ueber_mitternacht_ist_gueltig(self) -> None:
        form = SchichtvorlageForm(
            data={"name": "Nachtschicht", "beginn": "22:00", "ende": "06:00", "farbe": "#2563eb"},
            betrieb=BetriebFactory(),
        )
        self.assertTrue(form.is_valid(), form.errors)
        vorlage = form.save()
        self.assertEqual(vorlage.dauer_stunden, 8)

    def test_identischer_beginn_und_ende_ist_ungueltig(self) -> None:
        form = SchichtvorlageForm(
            data={"name": "Leer", "beginn": "08:00", "ende": "08:00", "farbe": "#2563eb"},
            betrieb=BetriebFactory(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_pflichtfelder_fehlen_ist_ungueltig(self) -> None:
        form = SchichtvorlageForm(data={"name": ""}, betrieb=BetriebFactory())
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("beginn", form.errors)
        self.assertIn("ende", form.errors)


class SchichtvorlageViewTests(TestCase):
    """Die Views arbeiten gegen den aktiven (ersten) Betrieb."""

    def setUp(self) -> None:
        # Name sortiert vor allen Zweit-Betrieben, damit aktueller_betrieb()
        # (Betrieb.objects.first(), Sortierung nach Name) deterministisch diesen wählt.
        self.betrieb = BetriebFactory(name="Aktiv-Betrieb")
        self.user = get_user_model().objects.create_user("planer", password="geheim123")
        self.client.force_login(self.user)

    def test_liste_zeigt_eigene_vorlagen(self) -> None:
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb, name="Frühdienst")
        antwort = self.client.get(reverse("planning:vorlage_liste"))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Frühdienst")
        self.assertEqual(list(antwort.context["vorlagen"]), [vorlage])

    def test_liste_zeigt_keine_fremden_vorlagen(self) -> None:
        SchichtvorlageFactory(betrieb=BetriebFactory(name="Zweit-Betrieb"), name="Fremddienst")
        antwort = self.client.get(reverse("planning:vorlage_liste"))
        self.assertNotContains(antwort, "Fremddienst")

    def test_anlegen_erstellt_vorlage_im_betrieb(self) -> None:
        antwort = self.client.post(
            reverse("planning:vorlage_neu"),
            {"name": "Spätschicht", "beginn": "14:00", "ende": "22:00",
             "benoetigte_rolle": "Fachkraft", "farbe": "#10b981"},
        )
        vorlage = Schichtvorlage.objects.get(name="Spätschicht")
        self.assertEqual(vorlage.betrieb, self.betrieb)
        self.assertEqual(vorlage.beginn, time(14, 0))
        self.assertRedirects(antwort, reverse("planning:vorlage_detail", args=[vorlage.pk]))

    def test_bearbeiten_aendert_daten(self) -> None:
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb, name="Frühdienst")
        self.client.post(
            reverse("planning:vorlage_bearbeiten", args=[vorlage.pk]),
            {"name": "Frühdienst", "beginn": "05:00", "ende": "13:00", "farbe": "#2563eb"},
        )
        vorlage.refresh_from_db()
        self.assertEqual(vorlage.beginn, time(5, 0))

    def test_loeschen_entfernt_vorlage(self) -> None:
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb)
        antwort = self.client.post(reverse("planning:vorlage_loeschen", args=[vorlage.pk]))
        self.assertRedirects(antwort, reverse("planning:vorlage_liste"))
        self.assertFalse(Schichtvorlage.objects.filter(pk=vorlage.pk).exists())

    def test_loeschen_nur_per_post(self) -> None:
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb)
        antwort = self.client.get(reverse("planning:vorlage_loeschen", args=[vorlage.pk]))
        self.assertEqual(antwort.status_code, 405)
        self.assertTrue(Schichtvorlage.objects.filter(pk=vorlage.pk).exists())

    def test_detail_fuer_fremde_vorlage_ist_404(self) -> None:
        fremd = SchichtvorlageFactory(betrieb=BetriebFactory(name="Zweit-Betrieb"))
        antwort = self.client.get(reverse("planning:vorlage_detail", args=[fremd.pk]))
        self.assertEqual(antwort.status_code, 404)

    def test_login_erforderlich(self) -> None:
        self.client.logout()
        antwort = self.client.get(reverse("planning:vorlage_liste"))
        self.assertEqual(antwort.status_code, 302)
        self.assertIn("/konto/anmelden/", antwort["Location"])
