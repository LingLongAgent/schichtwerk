"""Tests für Abwesenheiten/Urlaub (M7).

M7 erfasst je Mitarbeiter Abwesenheiten (Urlaub/Krank) über einen Zeitraum. Eine
Abwesenheit blockiert das Einteilen an den betroffenen Tagen und wird im
Wochengitter sichtbar. Geprüft werden vier Ebenen: das Modell (inklusiver
Zeitraum, ``umfasst``, DB-Bedingung ``bis >= von``), die Service-Logik
(``ist_abwesend``, blockiertes ``einteilen``, Gitter-Zuordnung), das Formular
(Validierung) und die Views (Login-Schutz, POST-only, Mandantengrenze, geblockte
Einteilung mit Fehlermeldung).

Der 22.06.2026 ist ein Montag; die Woche reicht bis 28.06.2026.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from . import services
from .factories import (
    AbwesenheitFactory,
    BetriebFactory,
    MitarbeiterFactory,
    SchichtvorlageFactory,
)
from .forms import AbwesenheitForm
from .models import Abwesenheit, Zuweisung
from .services import EinteilenBlockiert

MONTAG = date(2026, 6, 22)
DIENSTAG = date(2026, 6, 23)
SONNTAG = date(2026, 6, 28)


class AbwesenheitModellTests(TestCase):
    """Der inklusive Zeitraum und seine Tagesprüfung ``umfasst``."""

    def test_umfasst_grenztage_inklusive(self) -> None:
        abwesenheit = AbwesenheitFactory(von=MONTAG, bis=DIENSTAG)
        self.assertTrue(abwesenheit.umfasst(MONTAG))  # erster Tag zählt
        self.assertTrue(abwesenheit.umfasst(DIENSTAG))  # letzter Tag zählt
        self.assertFalse(abwesenheit.umfasst(date(2026, 6, 24)))

    def test_umfasst_tag_vor_beginn_false(self) -> None:
        abwesenheit = AbwesenheitFactory(von=DIENSTAG, bis=SONNTAG)
        self.assertFalse(abwesenheit.umfasst(MONTAG))

    def test_tage_zaehlt_inklusive(self) -> None:
        # Mo–So sind sieben Kalendertage, beide Enden eingeschlossen.
        self.assertEqual(AbwesenheitFactory(von=MONTAG, bis=SONNTAG).tage, 7)
        self.assertEqual(AbwesenheitFactory(von=MONTAG, bis=MONTAG).tage, 1)

    def test_art_anzeige_liefert_klartext(self) -> None:
        self.assertEqual(AbwesenheitFactory(art=Abwesenheit.KRANK).art_anzeige, "Krank")

    def test_bis_vor_von_verletzt_db_bedingung(self) -> None:
        with self.assertRaises(IntegrityError):
            Abwesenheit.objects.create(
                mitarbeiter=MitarbeiterFactory(), von=DIENSTAG, bis=MONTAG
            )


class IstAbwesendTests(TestCase):
    """Die Service-Abfrage ``ist_abwesend``."""

    def setUp(self) -> None:
        self.person = MitarbeiterFactory()

    def test_findet_abwesenheit_am_tag(self) -> None:
        abwesenheit = AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=DIENSTAG)
        self.assertEqual(services.ist_abwesend(self.person, MONTAG), abwesenheit)

    def test_kein_treffer_ausserhalb_des_zeitraums(self) -> None:
        AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=DIENSTAG)
        self.assertIsNone(services.ist_abwesend(self.person, SONNTAG))

    def test_andere_person_zaehlt_nicht(self) -> None:
        AbwesenheitFactory(mitarbeiter=MitarbeiterFactory(), von=MONTAG, bis=SONNTAG)
        self.assertIsNone(services.ist_abwesend(self.person, MONTAG))


class EinteilenMitAbwesenheitTests(TestCase):
    """Abwesenheit blockiert das Einteilen am betroffenen Tag."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.person = MitarbeiterFactory(betrieb=self.betrieb)
        self.vorlage = SchichtvorlageFactory(betrieb=self.betrieb)

    def test_einteilen_am_abwesenheitstag_blockiert(self) -> None:
        AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=DIENSTAG)
        with self.assertRaises(EinteilenBlockiert):
            services.einteilen(self.person, self.vorlage, MONTAG)
        self.assertEqual(Zuweisung.objects.count(), 0)

    def test_einteilen_ausserhalb_der_abwesenheit_erlaubt(self) -> None:
        AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=DIENSTAG)
        zuweisung = services.einteilen(self.person, self.vorlage, SONNTAG)
        self.assertEqual(zuweisung.schicht.datum, SONNTAG)
        self.assertEqual(Zuweisung.objects.count(), 1)


class WochengitterAbwesenheitTests(TestCase):
    """Das Gitter trägt die Abwesenheit in den betroffenen Tageszellen."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.person = MitarbeiterFactory(betrieb=self.betrieb)

    def test_zelle_traegt_abwesenheit(self) -> None:
        abwesenheit = AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=DIENSTAG)
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        zellen = gitter["zeilen"][0]["zellen"]
        self.assertEqual(zellen[0]["abwesenheit"], abwesenheit)  # Montag
        self.assertEqual(zellen[1]["abwesenheit"], abwesenheit)  # Dienstag
        self.assertIsNone(zellen[2]["abwesenheit"])  # Mittwoch frei

    def test_zellen_ohne_abwesenheit_bleiben_none(self) -> None:
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        zellen = gitter["zeilen"][0]["zellen"]
        self.assertTrue(all(zelle["abwesenheit"] is None for zelle in zellen))

    def test_abwesenheiten_je_woche_nur_im_fenster(self) -> None:
        tage = services.wochentage(MONTAG)
        AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=MONTAG)
        AbwesenheitFactory(mitarbeiter=self.person, von=date(2026, 7, 6), bis=date(2026, 7, 7))
        treffer = services.abwesenheiten_je_woche(self.betrieb, tage)
        self.assertEqual(list(treffer.keys()), [(self.person.id, MONTAG)])


class AbwesenheitFormTests(TestCase):
    """Validierung des Abwesenheits-Formulars."""

    def setUp(self) -> None:
        self.person = MitarbeiterFactory()

    def test_gueltige_eingabe(self) -> None:
        form = AbwesenheitForm(
            {"art": Abwesenheit.URLAUB, "von": MONTAG, "bis": DIENSTAG, "notiz": ""},
            mitarbeiter=self.person,
        )
        self.assertTrue(form.is_valid())
        abwesenheit = form.save()
        self.assertEqual(abwesenheit.mitarbeiter, self.person)

    def test_bis_vor_von_unzulaessig(self) -> None:
        form = AbwesenheitForm(
            {"art": Abwesenheit.URLAUB, "von": DIENSTAG, "bis": MONTAG, "notiz": ""},
            mitarbeiter=self.person,
        )
        self.assertFalse(form.is_valid())


class AbwesenheitViewTests(TestCase):
    """Die Views: Login-Schutz, POST-only, Mandantengrenze, geblockte Einteilung."""

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username="planer", password="geheim123")
        self.betrieb = services.aktueller_betrieb()
        self.person = MitarbeiterFactory(betrieb=self.betrieb, vorname="Mara", nachname="Lenz")
        self.vorlage = SchichtvorlageFactory(betrieb=self.betrieb, name="Frühschicht")

    def test_hinzufuegen_login_erforderlich(self) -> None:
        url = reverse("planning:abwesenheit_hinzufuegen", args=[self.person.pk])
        antwort = self.client.post(url, {"art": "urlaub", "von": MONTAG, "bis": DIENSTAG})
        self.assertEqual(antwort.status_code, 302)
        self.assertIn(reverse("login"), antwort["Location"])

    def test_hinzufuegen_nur_per_post(self) -> None:
        self.client.force_login(self.user)
        url = reverse("planning:abwesenheit_hinzufuegen", args=[self.person.pk])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_hinzufuegen_legt_abwesenheit_an(self) -> None:
        self.client.force_login(self.user)
        url = reverse("planning:abwesenheit_hinzufuegen", args=[self.person.pk])
        antwort = self.client.post(
            url, {"art": "urlaub", "von": MONTAG.isoformat(), "bis": DIENSTAG.isoformat(), "notiz": ""}
        )
        self.assertEqual(antwort.status_code, 302)
        self.assertEqual(self.person.abwesenheiten.count(), 1)

    def test_hinzufuegen_ungueltig_zeigt_formular(self) -> None:
        self.client.force_login(self.user)
        url = reverse("planning:abwesenheit_hinzufuegen", args=[self.person.pk])
        antwort = self.client.post(
            url, {"art": "urlaub", "von": DIENSTAG.isoformat(), "bis": MONTAG.isoformat()}
        )
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(self.person.abwesenheiten.count(), 0)

    def test_detail_zeigt_abwesenheit(self) -> None:
        AbwesenheitFactory(mitarbeiter=self.person, art=Abwesenheit.KRANK, von=MONTAG, bis=DIENSTAG)
        self.client.force_login(self.user)
        antwort = self.client.get(reverse("planning:mitarbeiter_detail", args=[self.person.pk]))
        self.assertContains(antwort, "Krank")

    def test_entfernen_loescht_abwesenheit(self) -> None:
        abwesenheit = AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=DIENSTAG)
        self.client.force_login(self.user)
        url = reverse("planning:abwesenheit_entfernen", args=[abwesenheit.pk])
        antwort = self.client.post(url)
        self.assertEqual(antwort.status_code, 302)
        self.assertFalse(Abwesenheit.objects.filter(pk=abwesenheit.pk).exists())

    def test_entfernen_fremde_abwesenheit_404(self) -> None:
        fremd = AbwesenheitFactory(mitarbeiter=MitarbeiterFactory(betrieb=BetriebFactory()))
        self.client.force_login(self.user)
        url = reverse("planning:abwesenheit_entfernen", args=[fremd.pk])
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(Abwesenheit.objects.filter(pk=fremd.pk).exists())

    def test_einteilung_am_abwesenheitstag_zeigt_fehler(self) -> None:
        AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=DIENSTAG)
        self.client.force_login(self.user)
        url = reverse("planning:einteilung_hinzufuegen", args=[self.person.pk, MONTAG.isoformat()])
        antwort = self.client.post(url, {"vorlage": self.vorlage.pk}, follow=True)
        self.assertEqual(Zuweisung.objects.count(), 0)
        self.assertContains(antwort, "abwesend")

    def test_einteilen_seite_zeigt_abwesenheits_hinweis(self) -> None:
        AbwesenheitFactory(mitarbeiter=self.person, von=MONTAG, bis=DIENSTAG)
        self.client.force_login(self.user)
        url = reverse("planning:einteilen_tag", args=[self.person.pk, MONTAG.isoformat()])
        antwort = self.client.get(url)
        self.assertContains(antwort, "Abwesend")
