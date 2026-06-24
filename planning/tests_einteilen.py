"""Tests für das Einteilen (M5).

M5 macht das Wochengitter bearbeitbar: Ein Mitarbeiter wird einer Schicht an
einem Tag zugewiesen oder wieder entfernt; unterbesetzte Schichten erscheinen als
„offen". Geprüft werden drei Ebenen: die idempotente Zuweisungs-Logik in
``services`` (legt Schicht bei Bedarf an, keine Doppelzuweisung), die Ermittlung
offener Schichten je Tag und die Views (Login-Schutz, POST-only, Mandantengrenze,
robustes Verhalten bei kaputtem Datum).

Der 22.06.2026 ist ein Montag; die Woche reicht bis 28.06.2026.
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
from .models import Schicht, Zuweisung

MONTAG = date(2026, 6, 22)
DIENSTAG = date(2026, 6, 23)


class EinteilenLogikTests(TestCase):
    """Die reine Zuweisungs-Logik: Schicht anlegen, idempotent zuweisen."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.person = MitarbeiterFactory(betrieb=self.betrieb)
        self.vorlage = SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(6, 0), ende=time(14, 0))

    def test_einteilen_legt_schicht_und_zuweisung_an(self) -> None:
        zuweisung = services.einteilen(self.person, self.vorlage, MONTAG)
        self.assertEqual(zuweisung.mitarbeiter, self.person)
        self.assertEqual(zuweisung.schicht.vorlage, self.vorlage)
        self.assertEqual(zuweisung.schicht.datum, MONTAG)
        self.assertEqual(Schicht.objects.count(), 1)
        self.assertEqual(Zuweisung.objects.count(), 1)

    def test_einteilen_ist_idempotent(self) -> None:
        # Zweimal dieselbe Einteilung darf keine Duplikate erzeugen.
        erste = services.einteilen(self.person, self.vorlage, MONTAG)
        zweite = services.einteilen(self.person, self.vorlage, MONTAG)
        self.assertEqual(erste.pk, zweite.pk)
        self.assertEqual(Zuweisung.objects.count(), 1)

    def test_einteilen_nutzt_bestehende_schicht(self) -> None:
        # Existiert die Tagesschicht bereits, wird sie wiederverwendet statt doppelt angelegt.
        schicht = SchichtFactory(vorlage=self.vorlage, datum=MONTAG)
        zuweisung = services.einteilen(self.person, self.vorlage, MONTAG)
        self.assertEqual(zuweisung.schicht, schicht)
        self.assertEqual(Schicht.objects.count(), 1)


class OffeneSchichtenTests(TestCase):
    """Offene (unterbesetzte) Schichten je Tag."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.tage = services.wochentage(MONTAG)

    def test_unbesetzte_schicht_gilt_als_offen(self) -> None:
        schicht = SchichtFactory(vorlage__betrieb=self.betrieb, datum=MONTAG, bedarf=1)
        offen = services.offene_schichten_je_tag(self.betrieb, self.tage)
        self.assertEqual(offen[MONTAG], [schicht])

    def test_voll_besetzte_schicht_ist_nicht_offen(self) -> None:
        schicht = SchichtFactory(vorlage__betrieb=self.betrieb, datum=MONTAG, bedarf=1)
        ZuweisungFactory(schicht=schicht, mitarbeiter=MitarbeiterFactory(betrieb=self.betrieb))
        offen = services.offene_schichten_je_tag(self.betrieb, self.tage)
        self.assertNotIn(MONTAG, offen)

    def test_teilbesetzte_schicht_bleibt_offen(self) -> None:
        schicht = SchichtFactory(vorlage__betrieb=self.betrieb, datum=MONTAG, bedarf=2)
        ZuweisungFactory(schicht=schicht, mitarbeiter=MitarbeiterFactory(betrieb=self.betrieb))
        offen = services.offene_schichten_je_tag(self.betrieb, self.tage)
        self.assertEqual(offen[MONTAG], [schicht])

    def test_offene_schichten_eines_tages_nach_beginn_sortiert(self) -> None:
        spaet = SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(14, 0), ende=time(22, 0))
        frueh = SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(6, 0), ende=time(14, 0))
        s_spaet = SchichtFactory(vorlage=spaet, datum=MONTAG)
        s_frueh = SchichtFactory(vorlage=frueh, datum=MONTAG)
        offen = services.offene_schichten_je_tag(self.betrieb, self.tage)
        self.assertEqual(offen[MONTAG], [s_frueh, s_spaet])

    def test_fremde_betriebe_und_andere_wochen_ignoriert(self) -> None:
        SchichtFactory(vorlage__betrieb=BetriebFactory(), datum=MONTAG)  # fremd
        SchichtFactory(vorlage__betrieb=self.betrieb, datum=date(2026, 7, 6))  # andere Woche
        offen = services.offene_schichten_je_tag(self.betrieb, self.tage)
        self.assertEqual(offen, {})


class TageszuteilungTests(TestCase):
    """Daten für die Einteilen-Seite: bestehende Zuweisungen + freie Vorlagen."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.person = MitarbeiterFactory(betrieb=self.betrieb)

    def test_bereits_zugewiesene_vorlage_ist_nicht_mehr_verfuegbar(self) -> None:
        belegt = SchichtvorlageFactory(betrieb=self.betrieb, name="Früh")
        frei = SchichtvorlageFactory(betrieb=self.betrieb, name="Spät")
        services.einteilen(self.person, belegt, MONTAG)
        daten = services.tageszuteilung(self.betrieb, self.person, MONTAG)
        self.assertEqual([z.schicht.vorlage for z in daten["zuweisungen"]], [belegt])
        self.assertEqual(list(daten["verfuegbar"]), [frei])

    def test_zuweisung_eines_anderen_tages_zaehlt_nicht(self) -> None:
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb)
        services.einteilen(self.person, vorlage, DIENSTAG)
        daten = services.tageszuteilung(self.betrieb, self.person, MONTAG)
        self.assertEqual(daten["zuweisungen"], [])
        self.assertEqual(list(daten["verfuegbar"]), [vorlage])


class WochengitterOffenTests(TestCase):
    """Das Gitter trägt offene Schichten als eigene Tagesspur."""

    def test_gitter_meldet_offene_schichten(self) -> None:
        betrieb = BetriebFactory()
        SchichtFactory(vorlage__betrieb=betrieb, datum=MONTAG, bedarf=1)
        gitter = services.wochengitter(betrieb, MONTAG, heute=MONTAG)
        self.assertTrue(gitter["hat_offene"])
        self.assertEqual(len(gitter["offen"]), 7)
        self.assertEqual(len(gitter["offen"][0]["schichten"]), 1)  # Montag
        self.assertEqual(gitter["offen"][1]["schichten"], [])  # Dienstag leer

    def test_gitter_ohne_offene_schichten(self) -> None:
        betrieb = BetriebFactory()
        gitter = services.wochengitter(betrieb, MONTAG, heute=MONTAG)
        self.assertFalse(gitter["hat_offene"])


class EinteilenViewTests(TestCase):
    """Die Views: Login-Schutz, POST-only, Mandantengrenze, Datums-Robustheit."""

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username="planer", password="geheim123")
        self.betrieb = services.aktueller_betrieb()
        self.person = MitarbeiterFactory(betrieb=self.betrieb, vorname="Mara", nachname="Lenz")
        self.vorlage = SchichtvorlageFactory(betrieb=self.betrieb, name="Frühschicht")

    def _url_seite(self, person=None, datum: date = MONTAG) -> str:
        person = person or self.person
        return reverse("planning:einteilen_tag", args=[person.pk, datum.isoformat()])

    def test_seite_login_erforderlich(self) -> None:
        antwort = self.client.get(self._url_seite())
        self.assertEqual(antwort.status_code, 302)
        self.assertIn(reverse("login"), antwort["Location"])

    def test_seite_zeigt_person_und_freie_vorlage(self) -> None:
        self.client.force_login(self.user)
        antwort = self.client.get(self._url_seite())
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Mara Lenz")
        self.assertContains(antwort, "Frühschicht")

    def test_seite_bei_kaputtem_datum_404(self) -> None:
        self.client.force_login(self.user)
        url = reverse("planning:einteilen_tag", args=[self.person.pk, "kein-datum"])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_seite_fremder_mitarbeiter_404(self) -> None:
        fremd = MitarbeiterFactory(betrieb=BetriebFactory())
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self._url_seite(person=fremd)).status_code, 404)

    def test_hinzufuegen_legt_zuweisung_an_und_leitet_um(self) -> None:
        self.client.force_login(self.user)
        url = reverse("planning:einteilung_hinzufuegen", args=[self.person.pk, MONTAG.isoformat()])
        antwort = self.client.post(url, {"vorlage": self.vorlage.pk})
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(Zuweisung.objects.filter(mitarbeiter=self.person).count(), 1)

    def test_hinzufuegen_nur_per_post(self) -> None:
        self.client.force_login(self.user)
        url = reverse("planning:einteilung_hinzufuegen", args=[self.person.pk, MONTAG.isoformat()])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_hinzufuegen_fremde_vorlage_404(self) -> None:
        fremd = SchichtvorlageFactory(betrieb=BetriebFactory())
        self.client.force_login(self.user)
        url = reverse("planning:einteilung_hinzufuegen", args=[self.person.pk, MONTAG.isoformat()])
        antwort = self.client.post(url, {"vorlage": fremd.pk})
        self.assertEqual(antwort.status_code, 404)
        self.assertEqual(Zuweisung.objects.count(), 0)

    def test_entfernen_loescht_zuweisung_und_leitet_um(self) -> None:
        zuweisung = services.einteilen(self.person, self.vorlage, MONTAG)
        self.client.force_login(self.user)
        url = reverse("planning:einteilung_entfernen", args=[zuweisung.pk])
        antwort = self.client.post(url)
        self.assertEqual(antwort.status_code, 302)
        self.assertFalse(Zuweisung.objects.filter(pk=zuweisung.pk).exists())

    def test_entfernen_nur_per_post(self) -> None:
        zuweisung = services.einteilen(self.person, self.vorlage, MONTAG)
        self.client.force_login(self.user)
        url = reverse("planning:einteilung_entfernen", args=[zuweisung.pk])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_entfernen_fremde_zuweisung_404(self) -> None:
        fremd_person = MitarbeiterFactory(betrieb=BetriebFactory())
        fremd_vorlage = SchichtvorlageFactory(betrieb=fremd_person.betrieb)
        zuweisung = services.einteilen(fremd_person, fremd_vorlage, MONTAG)
        self.client.force_login(self.user)
        url = reverse("planning:einteilung_entfernen", args=[zuweisung.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(Zuweisung.objects.filter(pk=zuweisung.pk).exists())
