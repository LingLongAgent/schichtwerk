"""Tests für die Übersichts-Kennzahlen (M9 · ``services.dashboard_daten``).

Geprüft wird die reine Aufbereitung der Wochenzahlen: dass die vier Kennzahlen
korrekt zählen, die Stunden je Mitarbeiter nur die Schichten der laufenden Woche
summieren und die Auslastung samt Überlast-Markierung stimmt, und dass die
Tagesbesetzung eingeteilte und offene Schichten je Wochentag richtig ausweist.
"""

from __future__ import annotations

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .factories import (
    BetriebFactory,
    MitarbeiterFactory,
    SchichtFactory,
    SchichtvorlageFactory,
    ZuweisungFactory,
)
from .services import dashboard_daten

# Eine feste Bezugswoche (Montag 22.06.2026) macht die Tests datumsstabil.
MONTAG = date(2026, 6, 22)
MITTWOCH = date(2026, 6, 24)
NAECHSTE_WOCHE = date(2026, 6, 29)


class DashboardDatenTest(TestCase):
    def setUp(self) -> None:
        self.betrieb = BetriebFactory()

    def _frueh_vorlage(self) -> object:
        """Frühschicht 06–14 Uhr (8 Stunden) im Test-Betrieb."""
        return SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(6, 0), ende=time(14, 0))

    def test_leerer_betrieb_liefert_nullen(self) -> None:
        daten = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)
        werte = {kpi["label"]: kpi["value"] for kpi in daten["kpis"]}
        self.assertEqual(werte["Mitarbeiter"], 0)
        self.assertEqual(werte["Schichten diese Woche"], 0)
        self.assertEqual(werte["Offene Schichten"], 0)
        self.assertEqual(werte["Konflikte"], 0)
        self.assertEqual(daten["stunden_zeilen"], [])
        self.assertEqual(len(daten["besetzung"]), 7)

    def test_kennzahl_mitarbeiter_zaehlt_nur_aktive(self) -> None:
        MitarbeiterFactory(betrieb=self.betrieb, aktiv=True)
        MitarbeiterFactory(betrieb=self.betrieb, aktiv=True)
        MitarbeiterFactory(betrieb=self.betrieb, aktiv=False)
        daten = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)
        werte = {kpi["label"]: kpi["value"] for kpi in daten["kpis"]}
        self.assertEqual(werte["Mitarbeiter"], 2)
        self.assertEqual(len(daten["stunden_zeilen"]), 2)

    def test_offene_und_geplante_schichten_der_woche(self) -> None:
        vorlage = self._frueh_vorlage()
        person = MitarbeiterFactory(betrieb=self.betrieb)
        besetzte = SchichtFactory(vorlage=vorlage, datum=MITTWOCH, bedarf=1)
        ZuweisungFactory(schicht=besetzte, mitarbeiter=person)
        SchichtFactory(vorlage=vorlage, datum=MONTAG, bedarf=1)  # offen, niemand zugewiesen
        daten = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)
        werte = {kpi["label"]: kpi["value"] for kpi in daten["kpis"]}
        self.assertEqual(werte["Schichten diese Woche"], 2)
        self.assertEqual(werte["Offene Schichten"], 1)

    def test_schichten_ausserhalb_der_woche_zaehlen_nicht(self) -> None:
        vorlage = self._frueh_vorlage()
        SchichtFactory(vorlage=vorlage, datum=NAECHSTE_WOCHE, bedarf=1)
        daten = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)
        werte = {kpi["label"]: kpi["value"] for kpi in daten["kpis"]}
        self.assertEqual(werte["Schichten diese Woche"], 0)
        self.assertEqual(werte["Offene Schichten"], 0)

    def test_stunden_je_mitarbeiter_summiert_nur_die_woche(self) -> None:
        vorlage = self._frueh_vorlage()  # 8 h
        person = MitarbeiterFactory(betrieb=self.betrieb, vertragsstunden=40)
        for tag in (MONTAG, MITTWOCH):
            schicht = SchichtFactory(vorlage=vorlage, datum=tag, bedarf=1)
            ZuweisungFactory(schicht=schicht, mitarbeiter=person)
        # Eine Schicht der Folgewoche darf die Summe nicht erhöhen.
        spaeter = SchichtFactory(vorlage=vorlage, datum=NAECHSTE_WOCHE, bedarf=1)
        ZuweisungFactory(schicht=spaeter, mitarbeiter=person)

        daten = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)
        zeile = daten["stunden_zeilen"][0]
        self.assertEqual(zeile["geplant"], 16.0)
        self.assertEqual(zeile["soll"], 40.0)
        self.assertEqual(zeile["auslastung"], 40)
        self.assertEqual(zeile["balken"], 40)
        self.assertFalse(zeile["ueberlastet"])

    def test_ueberlastung_kappt_balken_und_markiert(self) -> None:
        vorlage = self._frueh_vorlage()  # 8 h
        person = MitarbeiterFactory(betrieb=self.betrieb, vertragsstunden=10)
        for tag in (MONTAG, MITTWOCH):
            schicht = SchichtFactory(vorlage=vorlage, datum=tag, bedarf=1)
            ZuweisungFactory(schicht=schicht, mitarbeiter=person)

        zeile = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)["stunden_zeilen"][0]
        self.assertEqual(zeile["geplant"], 16.0)
        self.assertEqual(zeile["auslastung"], 160)
        self.assertEqual(zeile["balken"], 100)  # Balken nie über 100 %
        self.assertTrue(zeile["ueberlastet"])

    def test_stunden_zeilen_nach_geplant_absteigend(self) -> None:
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
        zeilen = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)["stunden_zeilen"]
        self.assertEqual(zeilen[0]["person"], viel)
        self.assertEqual(zeilen[1]["person"], wenig)

    def test_besetzung_je_tag_zaehlt_eingeteilt_und_offen(self) -> None:
        vorlage = self._frueh_vorlage()
        person = MitarbeiterFactory(betrieb=self.betrieb)
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=vorlage, datum=MITTWOCH, bedarf=1), mitarbeiter=person
        )
        SchichtFactory(vorlage=self._frueh_vorlage(), datum=MONTAG, bedarf=2)  # offen

        besetzung = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)["besetzung"]
        je_datum = {tag["datum"]: tag for tag in besetzung}
        self.assertEqual(je_datum[MITTWOCH]["eingeteilt"], 1)
        self.assertEqual(je_datum[MITTWOCH]["offen"], 0)
        self.assertTrue(je_datum[MITTWOCH]["ist_heute"])
        self.assertEqual(je_datum[MONTAG]["eingeteilt"], 0)
        self.assertEqual(je_datum[MONTAG]["offen"], 1)

    def test_konflikt_kennzahl_zaehlt_doppelbelegung(self) -> None:
        frueh = SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(6, 0), ende=time(14, 0))
        ueberlappend = SchichtvorlageFactory(
            betrieb=self.betrieb, beginn=time(10, 0), ende=time(18, 0)
        )
        person = MitarbeiterFactory(betrieb=self.betrieb)
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=frueh, datum=MITTWOCH, bedarf=1), mitarbeiter=person
        )
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=ueberlappend, datum=MITTWOCH, bedarf=1),
            mitarbeiter=person,
        )
        daten = dashboard_daten(self.betrieb, MONTAG, MITTWOCH)
        werte = {kpi["label"]: kpi["value"] for kpi in daten["kpis"]}
        self.assertGreaterEqual(werte["Konflikte"], 1)
        self.assertTrue(daten["hat_konflikte"])


class DashboardViewTest(TestCase):
    def setUp(self) -> None:
        get_user_model().objects.create_user(username="planer", password="test12345")
        self.client.login(username="planer", password="test12345")

    def test_redirects_anonymous(self) -> None:
        self.client.logout()
        antwort = self.client.get(reverse("dashboard"))
        self.assertEqual(antwort.status_code, 302)

    def test_zeigt_kennzahlen_und_mitarbeiter(self) -> None:
        from .services import aktueller_betrieb

        betrieb = aktueller_betrieb()
        MitarbeiterFactory(betrieb=betrieb, vorname="Anna", nachname="Beispiel")
        antwort = self.client.get(reverse("dashboard"))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Stunden je Mitarbeiter")
        self.assertContains(antwort, "Wochenbesetzung")
        self.assertContains(antwort, "Anna Beispiel")
