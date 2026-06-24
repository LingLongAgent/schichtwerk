"""Tests für die Stundenübersicht und den Plan-Export (M11).

Geprüft wird zweierlei, jeweils ohne Umweg über HTTP:

* ``services.stundenuebersicht`` — dass die geplanten Stunden je Mitarbeiter und
  Wochentag korrekt summiert werden, die Wochensumme und die Differenz zur
  Vertragszeit stimmen, die Tagessummen (Spaltensummen) passen und nur Schichten
  der laufenden Woche zählen.
* ``services.plan_export_zeilen`` / ``_stunden_dezimal`` — dass der CSV-Export
  je Zuweisung eine korrekt befüllte, stabil sortierte Zeile mit deutschem
  Dezimalkomma erzeugt.

Dazu kommen Integrationstests der beiden Views (Login-Schutz, gerenderte Seite,
korrekte CSV-Antwort).
"""

from __future__ import annotations

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .factories import (
    AbteilungFactory,
    BetriebFactory,
    MitarbeiterFactory,
    SchichtFactory,
    SchichtvorlageFactory,
    ZuweisungFactory,
)
from .services import (
    _stunden_dezimal,
    aktueller_betrieb,
    plan_export_zeilen,
    stundenuebersicht,
)

# Feste Bezugswoche (Montag 22.06.2026) macht die Tests datumsstabil.
MONTAG = date(2026, 6, 22)
DIENSTAG = date(2026, 6, 23)
MITTWOCH = date(2026, 6, 24)
NAECHSTE_WOCHE = date(2026, 6, 29)


class StundenuebersichtTest(TestCase):
    def setUp(self) -> None:
        self.betrieb = BetriebFactory()

    def _frueh_vorlage(self) -> object:
        """Frühschicht 06–14 Uhr (8 Stunden) im Test-Betrieb."""
        return SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(6, 0), ende=time(14, 0))

    def test_leerer_betrieb_liefert_nullen(self) -> None:
        daten = stundenuebersicht(self.betrieb, MONTAG, MITTWOCH)
        self.assertEqual(daten["zeilen"], [])
        self.assertEqual(daten["tagessummen"], [0.0] * 7)
        self.assertEqual(daten["gesamt"], 0.0)
        self.assertEqual(len(daten["kopf"]), 7)

    def test_nur_aktive_mitarbeiter(self) -> None:
        MitarbeiterFactory(betrieb=self.betrieb, aktiv=True)
        MitarbeiterFactory(betrieb=self.betrieb, aktiv=False)
        daten = stundenuebersicht(self.betrieb, MONTAG, MITTWOCH)
        self.assertEqual(len(daten["zeilen"]), 1)

    def test_stunden_je_tag_und_woche(self) -> None:
        vorlage = self._frueh_vorlage()  # 8 h
        person = MitarbeiterFactory(betrieb=self.betrieb, vertragsstunden=40)
        for tag in (MONTAG, MITTWOCH):
            ZuweisungFactory(
                schicht=SchichtFactory(vorlage=vorlage, datum=tag, bedarf=1), mitarbeiter=person
            )
        zeile = stundenuebersicht(self.betrieb, MONTAG, MITTWOCH)["zeilen"][0]
        # tage[0] = Montag (8 h), tage[2] = Mittwoch (8 h), Rest 0.
        self.assertEqual(zeile["tage"][0], 8.0)
        self.assertEqual(zeile["tage"][1], 0.0)
        self.assertEqual(zeile["tage"][2], 8.0)
        self.assertEqual(zeile["summe"], 16.0)
        self.assertEqual(zeile["soll"], 40.0)
        self.assertEqual(zeile["differenz"], -24.0)

    def test_mehrere_schichten_am_selben_tag_summieren(self) -> None:
        frueh = self._frueh_vorlage()  # 8 h
        spaet = SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(14, 0), ende=time(18, 0))
        person = MitarbeiterFactory(betrieb=self.betrieb)
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=frueh, datum=MONTAG, bedarf=1), mitarbeiter=person
        )
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=spaet, datum=MONTAG, bedarf=1), mitarbeiter=person
        )
        zeile = stundenuebersicht(self.betrieb, MONTAG, MITTWOCH)["zeilen"][0]
        self.assertEqual(zeile["tage"][0], 12.0)
        self.assertEqual(zeile["summe"], 12.0)

    def test_schichten_ausserhalb_der_woche_zaehlen_nicht(self) -> None:
        vorlage = self._frueh_vorlage()
        person = MitarbeiterFactory(betrieb=self.betrieb)
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=vorlage, datum=NAECHSTE_WOCHE, bedarf=1),
            mitarbeiter=person,
        )
        zeile = stundenuebersicht(self.betrieb, MONTAG, MITTWOCH)["zeilen"][0]
        self.assertEqual(zeile["summe"], 0.0)

    def test_positive_differenz_bei_mehrarbeit(self) -> None:
        vorlage = self._frueh_vorlage()  # 8 h
        person = MitarbeiterFactory(betrieb=self.betrieb, vertragsstunden=10)
        for tag in (MONTAG, DIENSTAG):
            ZuweisungFactory(
                schicht=SchichtFactory(vorlage=vorlage, datum=tag, bedarf=1), mitarbeiter=person
            )
        zeile = stundenuebersicht(self.betrieb, MONTAG, MITTWOCH)["zeilen"][0]
        self.assertEqual(zeile["summe"], 16.0)
        self.assertEqual(zeile["differenz"], 6.0)

    def test_tagessummen_und_gesamt(self) -> None:
        vorlage = self._frueh_vorlage()  # 8 h
        a = MitarbeiterFactory(betrieb=self.betrieb)
        b = MitarbeiterFactory(betrieb=self.betrieb)
        # Beide auf dieselbe Montagsschicht (Bedarf 2), nur a zusätzlich am Mittwoch.
        montagsschicht = SchichtFactory(vorlage=vorlage, datum=MONTAG, bedarf=2)
        ZuweisungFactory(schicht=montagsschicht, mitarbeiter=a)
        ZuweisungFactory(schicht=montagsschicht, mitarbeiter=b)
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=vorlage, datum=MITTWOCH, bedarf=1), mitarbeiter=a
        )
        daten = stundenuebersicht(self.betrieb, MONTAG, MITTWOCH)
        self.assertEqual(daten["tagessummen"][0], 16.0)  # Montag: 2 × 8 h
        self.assertEqual(daten["tagessummen"][2], 8.0)  # Mittwoch: 1 × 8 h
        self.assertEqual(daten["gesamt"], 24.0)

    def test_zeilen_nach_summe_absteigend(self) -> None:
        vorlage = self._frueh_vorlage()
        viel = MitarbeiterFactory(betrieb=self.betrieb, vorname="Viel", nachname="Arbeit")
        wenig = MitarbeiterFactory(betrieb=self.betrieb, vorname="Wenig", nachname="Arbeit")
        for tag in (MONTAG, MITTWOCH):
            ZuweisungFactory(
                schicht=SchichtFactory(vorlage=vorlage, datum=tag, bedarf=1), mitarbeiter=viel
            )
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=self._frueh_vorlage(), datum=MONTAG, bedarf=1),
            mitarbeiter=wenig,
        )
        zeilen = stundenuebersicht(self.betrieb, MONTAG, MITTWOCH)["zeilen"]
        self.assertEqual(zeilen[0]["person"], viel)
        self.assertEqual(zeilen[1]["person"], wenig)


class StundenDezimalTest(TestCase):
    def test_ganze_stunden_ohne_nachkomma(self) -> None:
        self.assertEqual(_stunden_dezimal(8.0), "8")

    def test_halbe_stunde_mit_komma(self) -> None:
        self.assertEqual(_stunden_dezimal(7.5), "7,5")

    def test_viertelstunde(self) -> None:
        self.assertEqual(_stunden_dezimal(0.25), "0,25")


class PlanExportZeilenTest(TestCase):
    def setUp(self) -> None:
        self.betrieb = BetriebFactory()

    def test_leerer_plan_liefert_keine_zeilen(self) -> None:
        self.assertEqual(plan_export_zeilen(self.betrieb, MONTAG), [])

    def test_zeile_traegt_alle_felder(self) -> None:
        abteilung = AbteilungFactory(betrieb=self.betrieb, name="Küche")
        vorlage = SchichtvorlageFactory(
            betrieb=self.betrieb,
            abteilung=abteilung,
            name="Früh",
            beginn=time(6, 0),
            ende=time(13, 30),  # 7,5 h
        )
        person = MitarbeiterFactory(
            betrieb=self.betrieb, vorname="Anna", nachname="Beispiel", rolle="Köchin"
        )
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=vorlage, datum=MONTAG, bedarf=1), mitarbeiter=person
        )
        zeile = plan_export_zeilen(self.betrieb, MONTAG)[0]
        self.assertEqual(
            zeile,
            ["2026-06-22", "Mo", "Anna Beispiel", "Köchin", "Küche", "Früh", "06:00", "13:30", "7,5"],
        )

    def test_ohne_abteilung_leeres_feld(self) -> None:
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb, abteilung=None)
        person = MitarbeiterFactory(betrieb=self.betrieb)
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=vorlage, datum=MONTAG, bedarf=1), mitarbeiter=person
        )
        zeile = plan_export_zeilen(self.betrieb, MONTAG)[0]
        self.assertEqual(zeile[4], "")  # Abteilung-Spalte

    def test_nur_zuweisungen_der_woche(self) -> None:
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb)
        person = MitarbeiterFactory(betrieb=self.betrieb)
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=vorlage, datum=NAECHSTE_WOCHE, bedarf=1),
            mitarbeiter=person,
        )
        self.assertEqual(plan_export_zeilen(self.betrieb, MONTAG), [])

    def test_sortierung_nach_datum_dann_beginn(self) -> None:
        frueh = SchichtvorlageFactory(betrieb=self.betrieb, name="Früh", beginn=time(6, 0), ende=time(14, 0))
        spaet = SchichtvorlageFactory(betrieb=self.betrieb, name="Spät", beginn=time(14, 0), ende=time(22, 0))
        person = MitarbeiterFactory(betrieb=self.betrieb)
        # Bewusst in „falscher" Reihenfolge anlegen.
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=spaet, datum=MITTWOCH, bedarf=1), mitarbeiter=person
        )
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=frueh, datum=MITTWOCH, bedarf=1), mitarbeiter=person
        )
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=frueh, datum=MONTAG, bedarf=1), mitarbeiter=person
        )
        zeilen = plan_export_zeilen(self.betrieb, MONTAG)
        reihenfolge = [(zeile[0], zeile[5]) for zeile in zeilen]
        self.assertEqual(
            reihenfolge,
            [("2026-06-22", "Früh"), ("2026-06-24", "Früh"), ("2026-06-24", "Spät")],
        )


class StundenViewTest(TestCase):
    def setUp(self) -> None:
        get_user_model().objects.create_user(username="planer", password="test12345")
        self.client.login(username="planer", password="test12345")

    def test_redirects_anonymous(self) -> None:
        self.client.logout()
        antwort = self.client.get(reverse("planning:stundenuebersicht"))
        self.assertEqual(antwort.status_code, 302)

    def test_zeigt_mitarbeiter_und_stunden(self) -> None:
        betrieb = aktueller_betrieb()
        MitarbeiterFactory(betrieb=betrieb, vorname="Anna", nachname="Beispiel")
        antwort = self.client.get(reverse("planning:stundenuebersicht"))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Geplante Stunden je Mitarbeiter")
        self.assertContains(antwort, "Anna Beispiel")
        self.assertContains(antwort, "CSV-Export")


class PlanExportViewTest(TestCase):
    def setUp(self) -> None:
        get_user_model().objects.create_user(username="planer", password="test12345")
        self.client.login(username="planer", password="test12345")

    def test_redirects_anonymous(self) -> None:
        self.client.logout()
        antwort = self.client.get(reverse("planning:plan_export"))
        self.assertEqual(antwort.status_code, 302)

    def test_liefert_csv_mit_kopf_und_zeile(self) -> None:
        betrieb = aktueller_betrieb()
        vorlage = SchichtvorlageFactory(betrieb=betrieb, name="Früh", beginn=time(6, 0), ende=time(14, 0))
        person = MitarbeiterFactory(betrieb=betrieb, vorname="Anna", nachname="Beispiel")
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=vorlage, datum=MONTAG, bedarf=1), mitarbeiter=person
        )
        antwort = self.client.get(reverse("planning:plan_export"), {"start": MONTAG.isoformat()})
        self.assertEqual(antwort.status_code, 200)
        self.assertIn("text/csv", antwort["Content-Type"])
        self.assertIn("attachment;", antwort["Content-Disposition"])
        self.assertIn("dienstplan_2026-06-22.csv", antwort["Content-Disposition"])
        inhalt = antwort.content.decode("utf-8")
        self.assertTrue(inhalt.startswith("﻿"))  # BOM für Excel
        self.assertIn("Mitarbeiter;", inhalt)  # Semikolon-getrennter Kopf
        self.assertIn("Anna Beispiel;", inhalt)

    def test_leere_woche_liefert_nur_kopf(self) -> None:
        antwort = self.client.get(reverse("planning:plan_export"), {"start": MONTAG.isoformat()})
        zeilen = [z for z in antwort.content.decode("utf-8").splitlines() if z.strip()]
        self.assertEqual(len(zeilen), 1)  # nur die Kopfzeile
