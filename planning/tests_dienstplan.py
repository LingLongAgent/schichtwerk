"""Tests für das Dienstplan-Wochengitter (M4).

Zwei Ebenen werden geprüft: die reine Aufbereitungs-Logik in ``services``
(Wochenberechnung, Parsen des Query-Parameters, Zuordnung der Zuweisungen zu den
richtigen (Mitarbeiter, Tag)-Zellen) und die View (Login-Schutz, Anzeige der
gewählten Woche, robustes Verhalten bei kaputtem Parameter).

Alle Daten sind fest gewählt, damit die Tests unabhängig vom Kalender laufen.
Der 22.06.2026 ist ein Montag; die zugehörige Woche reicht bis 28.06.2026.
"""

from __future__ import annotations

from datetime import date, time, timedelta

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

MONTAG = date(2026, 6, 22)
SONNTAG = date(2026, 6, 28)


def _zuweisung_anlegen(betrieb, person, datum: date, beginn: time = time(6, 0)):
    """Eine Schicht der gewünschten Uhrzeit am Tag erzeugen und ``person`` zuweisen."""
    vorlage = SchichtvorlageFactory(betrieb=betrieb, beginn=beginn, ende=time(14, 0))
    schicht = SchichtFactory(vorlage=vorlage, datum=datum)
    return ZuweisungFactory(schicht=schicht, mitarbeiter=person)


class WochenLogikTests(TestCase):
    """Die reinen Datums-Helfer rund um die Kalenderwoche."""

    def test_wochenstart_ist_immer_montag(self) -> None:
        # Mittwoch (24.) und Sonntag (28.) liegen beide in der Woche ab Montag 22.
        self.assertEqual(services.wochenstart(date(2026, 6, 24)), MONTAG)
        self.assertEqual(services.wochenstart(SONNTAG), MONTAG)
        self.assertEqual(services.wochenstart(MONTAG), MONTAG)

    def test_wochentage_liefert_montag_bis_sonntag(self) -> None:
        tage = services.wochentage(MONTAG)
        self.assertEqual(len(tage), 7)
        self.assertEqual(tage[0], MONTAG)
        self.assertEqual(tage[-1], SONNTAG)

    def test_parse_wochenstart_nimmt_gueltiges_datum(self) -> None:
        start = services.parse_wochenstart("2026-06-24", heute=date(2026, 1, 1))
        self.assertEqual(start, MONTAG)

    def test_parse_wochenstart_faellt_bei_unsinn_auf_heutige_woche_zurueck(self) -> None:
        start = services.parse_wochenstart("kein-datum", heute=date(2026, 6, 24))
        self.assertEqual(start, MONTAG)

    def test_parse_wochenstart_ohne_parameter_nimmt_heutige_woche(self) -> None:
        start = services.parse_wochenstart(None, heute=SONNTAG)
        self.assertEqual(start, MONTAG)


class WochengitterTests(TestCase):
    """Aufbau des Gitters: nur aktive, eigene Mitarbeiter; Schichten am richtigen Tag."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()

    def test_kopf_hat_sieben_tage_mit_kuerzeln_und_wochenende(self) -> None:
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        kopf = gitter["kopf"]
        self.assertEqual([t["kuerzel"] for t in kopf], services.WOCHENTAG_KUERZEL)
        self.assertFalse(kopf[0]["ist_wochenende"])
        self.assertTrue(kopf[5]["ist_wochenende"])
        self.assertTrue(kopf[6]["ist_wochenende"])

    def test_nur_aktive_mitarbeiter_als_zeilen(self) -> None:
        aktiv = MitarbeiterFactory(betrieb=self.betrieb, aktiv=True)
        MitarbeiterFactory(betrieb=self.betrieb, aktiv=False)
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        personen = [zeile["person"] for zeile in gitter["zeilen"]]
        self.assertEqual(personen, [aktiv])

    def test_fremde_mitarbeiter_erscheinen_nicht(self) -> None:
        eigener = MitarbeiterFactory(betrieb=self.betrieb)
        MitarbeiterFactory(betrieb=BetriebFactory())
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        self.assertEqual([z["person"] for z in gitter["zeilen"]], [eigener])

    def test_zuweisung_landet_in_der_richtigen_tageszelle(self) -> None:
        person = MitarbeiterFactory(betrieb=self.betrieb)
        mittwoch = date(2026, 6, 24)
        _zuweisung_anlegen(self.betrieb, person, mittwoch)
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        zellen = gitter["zeilen"][0]["zellen"]
        self.assertEqual(zellen[0]["schichten"], [])  # Montag leer
        self.assertEqual(len(zellen[2]["schichten"]), 1)  # Mittwoch belegt
        self.assertEqual(zellen[2]["datum"], mittwoch)

    def test_schichten_einer_zelle_nach_beginn_sortiert(self) -> None:
        person = MitarbeiterFactory(betrieb=self.betrieb)
        montag = MONTAG
        _zuweisung_anlegen(self.betrieb, person, montag, beginn=time(14, 0))
        _zuweisung_anlegen(self.betrieb, person, montag, beginn=time(6, 0))
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        schichten = gitter["zeilen"][0]["zellen"][0]["schichten"]
        self.assertEqual([s.beginn for s in schichten], [time(6, 0), time(14, 0)])

    def test_schichten_ausserhalb_der_woche_ignoriert(self) -> None:
        person = MitarbeiterFactory(betrieb=self.betrieb)
        _zuweisung_anlegen(self.betrieb, person, MONTAG - timedelta(days=1))
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        belegte = [z for zeile in gitter["zeilen"] for z in zeile["zellen"] if z["schichten"]]
        self.assertEqual(belegte, [])

    def test_heute_wird_in_kopf_und_zelle_markiert(self) -> None:
        MitarbeiterFactory(betrieb=self.betrieb)  # eine Zeile, damit Zellen existieren
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=date(2026, 6, 24))
        heute_kopf = [t for t in gitter["kopf"] if t["ist_heute"]]
        self.assertEqual([t["datum"] for t in heute_kopf], [date(2026, 6, 24)])
        zellen = gitter["zeilen"][0]["zellen"]
        self.assertTrue(zellen[2]["ist_heute"])
        self.assertFalse(zellen[0]["ist_heute"])


class WochengitterKonfliktTests(TestCase):
    """Das Gitter reicht die Arbeitszeit-Konflikte (M6) an die Oberfläche durch.

    Die Regel-Logik selbst ist in ``tests_regeln`` erschöpfend geprüft; hier geht
    es nur darum, dass ``wochengitter`` die Konflikte korrekt einsammelt, je
    Zeile zuordnet und die betroffenen Schicht-IDs zum Hervorheben bereitstellt.
    """

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.person = MitarbeiterFactory(betrieb=self.betrieb)

    def _einteilen(self, datum: date, beginn: time, ende: time):
        """``self.person`` an ``datum`` einer Schicht mit dem Zeitfenster zuweisen."""
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb, beginn=beginn, ende=ende)
        schicht = SchichtFactory(vorlage=vorlage, datum=datum)
        return ZuweisungFactory(schicht=schicht, mitarbeiter=self.person)

    def test_konfliktfreie_woche_ohne_warnung(self) -> None:
        self._einteilen(MONTAG, time(6, 0), time(14, 0))
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        self.assertFalse(gitter["hat_konflikte"])
        self.assertEqual(gitter["konflikte"], [])
        self.assertEqual(gitter["konflikt_schicht_ids"], set())
        self.assertEqual(gitter["zeilen"][0]["konflikte"], [])

    def test_ruhezeitverstoss_erscheint_im_gitter(self) -> None:
        # Spät Mo bis 22:00, Früh Di ab 06:00 -> nur 8 h Ruhe (< 11 h).
        spaet = self._einteilen(MONTAG, time(14, 0), time(22, 0))
        frueh = self._einteilen(date(2026, 6, 23), time(6, 0), time(14, 0))
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        self.assertTrue(gitter["hat_konflikte"])
        uebersicht = gitter["konflikte"]
        self.assertEqual([e["person"] for e in uebersicht], [self.person])
        self.assertEqual(uebersicht[0]["konflikte"][0].art, "ruhezeit")
        # Beide beteiligten Schichten werden zum Hervorheben gemeldet.
        self.assertEqual(
            gitter["konflikt_schicht_ids"], {spaet.schicht_id, frueh.schicht_id}
        )
        # Die Zeile des Mitarbeiters trägt denselben Konflikt.
        self.assertEqual(gitter["zeilen"][0]["konflikte"], uebersicht[0]["konflikte"])

    def test_nur_betroffene_mitarbeiter_in_uebersicht(self) -> None:
        ohne = MitarbeiterFactory(betrieb=self.betrieb)
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb, beginn=time(6, 0), ende=time(14, 0))
        ZuweisungFactory(schicht=SchichtFactory(vorlage=vorlage, datum=MONTAG), mitarbeiter=ohne)
        self._einteilen(MONTAG, time(14, 0), time(22, 0))
        self._einteilen(date(2026, 6, 23), time(6, 0), time(14, 0))
        gitter = services.wochengitter(self.betrieb, MONTAG, heute=MONTAG)
        self.assertEqual([e["person"] for e in gitter["konflikte"]], [self.person])


class DienstplanViewTests(TestCase):
    """Die View bindet Logik, Login-Schutz und Wochen-Navigation zusammen."""

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username="planer", password="geheim123")
        self.url = reverse("planning:schedule")

    def test_login_erforderlich(self) -> None:
        antwort = self.client.get(self.url)
        self.assertEqual(antwort.status_code, 302)
        self.assertIn(reverse("login"), antwort["Location"])

    def test_zeigt_aktive_mitarbeiter_im_gitter(self) -> None:
        person = MitarbeiterFactory(betrieb=services.aktueller_betrieb(), vorname="Mara", nachname="Lenz")
        self.client.force_login(self.user)
        antwort = self.client.get(self.url)
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, person.voller_name)

    def test_start_parameter_waehlt_gewuenschte_woche(self) -> None:
        self.client.force_login(self.user)
        antwort = self.client.get(self.url, {"start": "2026-06-24"})
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(antwort.context["gitter"]["start"], MONTAG)
        self.assertEqual(antwort.context["gitter"]["ende"], SONNTAG)

    def test_kaputter_start_parameter_fuehrt_nicht_zu_fehler(self) -> None:
        self.client.force_login(self.user)
        antwort = self.client.get(self.url, {"start": "01.01.2026"})
        self.assertEqual(antwort.status_code, 200)

    def test_konflikt_wird_in_der_warnkarte_angezeigt(self) -> None:
        betrieb = services.aktueller_betrieb()
        person = MitarbeiterFactory(betrieb=betrieb, vorname="Tom", nachname="Berg")
        spaet = SchichtvorlageFactory(betrieb=betrieb, beginn=time(14, 0), ende=time(22, 0))
        frueh = SchichtvorlageFactory(betrieb=betrieb, beginn=time(6, 0), ende=time(14, 0))
        ZuweisungFactory(schicht=SchichtFactory(vorlage=spaet, datum=MONTAG), mitarbeiter=person)
        ZuweisungFactory(
            schicht=SchichtFactory(vorlage=frueh, datum=date(2026, 6, 23)), mitarbeiter=person
        )
        self.client.force_login(self.user)
        antwort = self.client.get(self.url, {"start": MONTAG.isoformat()})
        self.assertEqual(antwort.status_code, 200)
        self.assertTrue(antwort.context["gitter"]["hat_konflikte"])
        self.assertContains(antwort, "Ruhezeit")
