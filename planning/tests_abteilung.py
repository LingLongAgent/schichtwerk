"""Tests für die Abteilungsverwaltung und den Abteilungs-Filter im Plan (M8).

Geprüft werden das Formular (Eindeutigkeit je Betrieb ohne Rücksicht auf
Groß-/Kleinschreibung, Setzen des Betriebs), die CRUD-Views inklusive
Login-Schutz, Mandanten-Scoping und schonendem Löschen (SET_NULL), sowie die
Service-Logik, mit der das Wochengitter und die offenen Schichten auf eine
Abteilung eingeschränkt werden.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import services
from .factories import (
    AbteilungFactory,
    BetriebFactory,
    MitarbeiterFactory,
    SchichtFactory,
    SchichtvorlageFactory,
)
from .forms import AbteilungForm
from .models import Abteilung


class AbteilungFormTests(TestCase):
    """Das Formular setzt den Betrieb und schützt die Eindeutigkeit des Namens."""

    def test_save_setzt_betrieb(self) -> None:
        betrieb = BetriebFactory()
        form = AbteilungForm(data={"name": "Küche"}, betrieb=betrieb)
        self.assertTrue(form.is_valid(), form.errors)
        abteilung = form.save()
        self.assertEqual(abteilung.betrieb, betrieb)
        self.assertEqual(abteilung.name, "Küche")

    def test_doppelter_name_wird_abgewiesen(self) -> None:
        betrieb = BetriebFactory()
        AbteilungFactory(betrieb=betrieb, name="Küche")
        form = AbteilungForm(data={"name": "Küche"}, betrieb=betrieb)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_doppelter_name_ist_case_insensitiv(self) -> None:
        betrieb = BetriebFactory()
        AbteilungFactory(betrieb=betrieb, name="Küche")
        form = AbteilungForm(data={"name": "küche"}, betrieb=betrieb)
        self.assertFalse(form.is_valid())

    def test_gleicher_name_in_anderem_betrieb_erlaubt(self) -> None:
        AbteilungFactory(betrieb=BetriebFactory(), name="Küche")
        form = AbteilungForm(data={"name": "Küche"}, betrieb=BetriebFactory())
        self.assertTrue(form.is_valid(), form.errors)

    def test_bearbeiten_mit_unveraendertem_namen_erlaubt(self) -> None:
        betrieb = BetriebFactory()
        abteilung = AbteilungFactory(betrieb=betrieb, name="Küche")
        form = AbteilungForm(data={"name": "Küche"}, instance=abteilung, betrieb=betrieb)
        self.assertTrue(form.is_valid(), form.errors)


class AbteilungFilterServiceTests(TestCase):
    """``abteilung_filter`` löst den Query-Parameter robust auf."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.abteilung = AbteilungFactory(betrieb=self.betrieb, name="Küche")

    def test_gueltige_id_liefert_abteilung(self) -> None:
        treffer = services.abteilung_filter(self.betrieb, str(self.abteilung.id))
        self.assertEqual(treffer, self.abteilung)

    def test_fehlender_parameter_liefert_none(self) -> None:
        self.assertIsNone(services.abteilung_filter(self.betrieb, None))
        self.assertIsNone(services.abteilung_filter(self.betrieb, ""))

    def test_unsinniger_parameter_liefert_none(self) -> None:
        self.assertIsNone(services.abteilung_filter(self.betrieb, "abc"))

    def test_fremde_abteilung_liefert_none(self) -> None:
        fremde = AbteilungFactory(betrieb=BetriebFactory(), name="Empfang")
        self.assertIsNone(services.abteilung_filter(self.betrieb, str(fremde.id)))


class WochengitterFilterTests(TestCase):
    """Das Wochengitter lässt sich auf eine Abteilung einschränken."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.kueche = AbteilungFactory(betrieb=self.betrieb, name="Küche")
        self.empfang = AbteilungFactory(betrieb=self.betrieb, name="Empfang")
        self.heute = date(2026, 6, 24)
        self.start = services.wochenstart(self.heute)

    def _personen(self, abteilung: Abteilung | None) -> list:
        gitter = services.wochengitter(self.betrieb, self.start, self.heute, abteilung)
        return [zeile["person"] for zeile in gitter["zeilen"]]

    def test_ohne_filter_alle_mitarbeiter(self) -> None:
        koch = MitarbeiterFactory(betrieb=self.betrieb, abteilung=self.kueche)
        pfoertner = MitarbeiterFactory(betrieb=self.betrieb, abteilung=self.empfang)
        personen = self._personen(None)
        self.assertIn(koch, personen)
        self.assertIn(pfoertner, personen)

    def test_filter_zeigt_nur_mitarbeiter_der_abteilung(self) -> None:
        koch = MitarbeiterFactory(betrieb=self.betrieb, abteilung=self.kueche)
        pfoertner = MitarbeiterFactory(betrieb=self.betrieb, abteilung=self.empfang)
        personen = self._personen(self.kueche)
        self.assertEqual(personen, [koch])
        self.assertNotIn(pfoertner, personen)

    def test_offene_schichten_nach_abteilung_gefiltert(self) -> None:
        tag = self.start
        kueche_vorlage = SchichtvorlageFactory(betrieb=self.betrieb, abteilung=self.kueche)
        empfang_vorlage = SchichtvorlageFactory(betrieb=self.betrieb, abteilung=self.empfang)
        SchichtFactory(vorlage=kueche_vorlage, datum=tag, bedarf=1)
        SchichtFactory(vorlage=empfang_vorlage, datum=tag, bedarf=1)
        gefiltert = services.offene_schichten_je_tag(self.betrieb, [tag], self.kueche)
        vorlagen = {schicht.vorlage_id for schicht in gefiltert.get(tag, [])}
        self.assertEqual(vorlagen, {kueche_vorlage.id})


class AbteilungViewTests(TestCase):
    """Die CRUD-Views sind login-geschützt und auf den aktiven Betrieb gescoped."""

    def setUp(self) -> None:
        self.betrieb = services.aktueller_betrieb()
        self.user = get_user_model().objects.create_user("planer", password="geheim123")
        self.client.force_login(self.user)

    def test_liste_braucht_login(self) -> None:
        self.client.logout()
        antwort = self.client.get(reverse("planning:abteilung_liste"))
        self.assertEqual(antwort.status_code, 302)

    def test_liste_zeigt_eigene_abteilungen_mit_zaehlern(self) -> None:
        kueche = AbteilungFactory(betrieb=self.betrieb, name="Küche")
        MitarbeiterFactory(betrieb=self.betrieb, abteilung=kueche)
        SchichtvorlageFactory(betrieb=self.betrieb, abteilung=kueche)
        antwort = self.client.get(reverse("planning:abteilung_liste"))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Küche")
        eintrag = antwort.context["abteilungen"].get(pk=kueche.pk)
        self.assertEqual(eintrag.anzahl_mitarbeiter, 1)
        self.assertEqual(eintrag.anzahl_vorlagen, 1)

    def test_neu_legt_abteilung_an(self) -> None:
        antwort = self.client.post(reverse("planning:abteilung_neu"), {"name": "Lager"})
        self.assertRedirects(antwort, reverse("planning:abteilung_liste"))
        self.assertTrue(Abteilung.objects.filter(betrieb=self.betrieb, name="Lager").exists())

    def test_bearbeiten_benennt_um(self) -> None:
        abteilung = AbteilungFactory(betrieb=self.betrieb, name="Kueche")
        antwort = self.client.post(
            reverse("planning:abteilung_bearbeiten", args=[abteilung.pk]), {"name": "Küche"}
        )
        self.assertRedirects(antwort, reverse("planning:abteilung_liste"))
        abteilung.refresh_from_db()
        self.assertEqual(abteilung.name, "Küche")

    def test_fremde_abteilung_nicht_bearbeitbar(self) -> None:
        fremde = AbteilungFactory(betrieb=BetriebFactory(name="Zweit"), name="Empfang")
        antwort = self.client.get(reverse("planning:abteilung_bearbeiten", args=[fremde.pk]))
        self.assertEqual(antwort.status_code, 404)

    def test_loeschen_entfernt_abteilung_und_schont_bezuege(self) -> None:
        abteilung = AbteilungFactory(betrieb=self.betrieb, name="Küche")
        person = MitarbeiterFactory(betrieb=self.betrieb, abteilung=abteilung)
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb, abteilung=abteilung)
        antwort = self.client.post(reverse("planning:abteilung_loeschen", args=[abteilung.pk]))
        self.assertRedirects(antwort, reverse("planning:abteilung_liste"))
        self.assertFalse(Abteilung.objects.filter(pk=abteilung.pk).exists())
        person.refresh_from_db()
        vorlage.refresh_from_db()
        self.assertIsNone(person.abteilung)
        self.assertIsNone(vorlage.abteilung)

    def test_loeschen_nur_per_post(self) -> None:
        abteilung = AbteilungFactory(betrieb=self.betrieb, name="Küche")
        antwort = self.client.get(reverse("planning:abteilung_loeschen", args=[abteilung.pk]))
        self.assertEqual(antwort.status_code, 405)

    def test_schedule_filter_zeigt_nur_abteilungs_mitarbeiter(self) -> None:
        kueche = AbteilungFactory(betrieb=self.betrieb, name="Küche")
        empfang = AbteilungFactory(betrieb=self.betrieb, name="Empfang")
        MitarbeiterFactory(betrieb=self.betrieb, abteilung=kueche, vorname="Koch", nachname="Eins")
        MitarbeiterFactory(betrieb=self.betrieb, abteilung=empfang, vorname="Pfoertner", nachname="Zwei")
        antwort = self.client.get(reverse("planning:schedule"), {"abteilung": kueche.id})
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Koch Eins")
        self.assertNotContains(antwort, "Pfoertner Zwei")
        self.assertEqual(antwort.context["aktive_abteilung"], kueche)
