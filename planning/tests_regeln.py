"""Tests der Arbeitszeit-Regeln (M6).

Der Schwerpunkt liegt auf der reinen Logik: Überlappung, Ruhezeit und
Wochenstunden werden an konstruierten ``Schichtzeit``-Werten geprüft, inklusive
der kniffligen Fälle (Nachtschicht über Mitternacht, exakt angrenzende
Schichten, Grenze der Ruhezeit). Ein schlankerer DB-Test sichert ab, dass der
``wochenkonflikte``-Wrapper die richtigen Zuweisungen lädt und gruppiert.
"""

from __future__ import annotations

from datetime import date, datetime, time

from django.test import TestCase

from .factories import (
    BetriebFactory,
    MitarbeiterFactory,
    SchichtFactory,
    SchichtvorlageFactory,
    ZuweisungFactory,
)
from .regeln import (
    MAX_WOCHENSTUNDEN,
    MIN_RUHEZEIT_STUNDEN,
    Schichtzeit,
    pruefe_schichten,
    ruhezeit_verletzungen,
    ueberlappungen,
    wochenkonflikte,
    wochenstunden_konflikt,
)


def _zeit(schicht_id: int, tag: date, beginn: time, ende: time, name: str = "Schicht") -> Schichtzeit:
    """Eine ``Schichtzeit`` bauen; Ende <= Beginn bedeutet Nachtschicht (Folgetag)."""
    start = datetime.combine(tag, beginn)
    schluss = datetime.combine(tag, ende)
    if ende <= beginn:
        schluss = datetime.combine(date.fromordinal(tag.toordinal() + 1), ende)
    return Schichtzeit(schicht_id=schicht_id, name=name, beginn=start, ende=schluss)


MONTAG = date(2026, 6, 22)
DIENSTAG = date(2026, 6, 23)


class UeberlappungTests(TestCase):
    def test_getrennte_schichten_kollidieren_nicht(self) -> None:
        frueh = _zeit(1, MONTAG, time(6, 0), time(14, 0))
        spaet = _zeit(2, MONTAG, time(14, 0), time(22, 0))
        self.assertEqual(ueberlappungen([frueh, spaet]), [])

    def test_ueberlappende_schichten_werden_erkannt(self) -> None:
        a = _zeit(1, MONTAG, time(6, 0), time(14, 0), "Früh")
        b = _zeit(2, MONTAG, time(12, 0), time(20, 0), "Spät")
        konflikte = ueberlappungen([a, b])
        self.assertEqual(len(konflikte), 1)
        self.assertEqual(konflikte[0].art, "ueberlappung")
        self.assertEqual(set(konflikte[0].schicht_ids), {1, 2})

    def test_aneinander_angrenzend_ist_keine_ueberlappung(self) -> None:
        # Ende 14:00 == Beginn 14:00 darf nicht als Überschneidung zählen.
        a = _zeit(1, MONTAG, time(6, 0), time(14, 0))
        b = _zeit(2, MONTAG, time(14, 0), time(22, 0))
        self.assertEqual(ueberlappungen([a, b]), [])

    def test_nachtschicht_ueberlappt_in_den_folgetag(self) -> None:
        nacht = _zeit(1, MONTAG, time(22, 0), time(6, 0), "Nacht")  # bis Di 06:00
        frueh = _zeit(2, DIENSTAG, time(5, 0), time(13, 0), "Früh")  # ab Di 05:00
        konflikte = ueberlappungen([nacht, frueh])
        self.assertEqual(len(konflikte), 1)
        self.assertEqual(set(konflikte[0].schicht_ids), {1, 2})

    def test_reihenfolge_der_eingabe_egal(self) -> None:
        a = _zeit(1, MONTAG, time(6, 0), time(14, 0))
        b = _zeit(2, MONTAG, time(12, 0), time(20, 0))
        self.assertEqual(len(ueberlappungen([b, a])), 1)


class RuhezeitTests(TestCase):
    def test_ausreichende_ruhezeit_ist_ok(self) -> None:
        mo = _zeit(1, MONTAG, time(6, 0), time(14, 0))
        di = _zeit(2, DIENSTAG, time(6, 0), time(14, 0))  # 16 h Pause
        self.assertEqual(ruhezeit_verletzungen([mo, di]), [])

    def test_zu_kurze_ruhezeit_wird_gemeldet(self) -> None:
        # Spät bis 22:00, Früh ab 06:00 -> nur 8 h Ruhe (< 11 h).
        spaet = _zeit(1, MONTAG, time(14, 0), time(22, 0), "Spät")
        frueh = _zeit(2, DIENSTAG, time(6, 0), time(14, 0), "Früh")
        konflikte = ruhezeit_verletzungen([spaet, frueh])
        self.assertEqual(len(konflikte), 1)
        self.assertEqual(konflikte[0].art, "ruhezeit")
        self.assertEqual(set(konflikte[0].schicht_ids), {1, 2})

    def test_genau_elf_stunden_sind_erlaubt(self) -> None:
        spaet = _zeit(1, MONTAG, time(11, 0), time(19, 0))
        frueh = _zeit(2, DIENSTAG, time(6, 0), time(14, 0))  # exakt 11 h Pause
        self.assertEqual(ruhezeit_verletzungen([spaet, frueh]), [])

    def test_ueberlappung_zaehlt_nicht_als_ruhezeitverstoss(self) -> None:
        a = _zeit(1, MONTAG, time(6, 0), time(14, 0))
        b = _zeit(2, MONTAG, time(12, 0), time(20, 0))
        self.assertEqual(ruhezeit_verletzungen([a, b]), [])

    def test_pause_wird_zum_spaetesten_ende_gemessen(self) -> None:
        # Lange Schicht 06–20 deckt die kurze 08–12 ab; danach nur 9 h bis 05:00.
        lang = _zeit(1, MONTAG, time(6, 0), time(20, 0), "Lang")
        kurz = _zeit(2, MONTAG, time(8, 0), time(12, 0), "Kurz")
        frueh = _zeit(3, DIENSTAG, time(5, 0), time(9, 0), "Früh")
        konflikte = ruhezeit_verletzungen([lang, kurz, frueh])
        self.assertEqual(len(konflikte), 1)
        # Gemessen ab dem späteren Ende (Lang 20:00), nicht ab Kurz 12:00.
        self.assertEqual(set(konflikte[0].schicht_ids), {1, 3})


class WochenstundenTests(TestCase):
    def test_unter_grenze_kein_konflikt(self) -> None:
        zeiten = [_zeit(i, MONTAG, time(6, 0), time(14, 0)) for i in range(5)]  # 40 h
        self.assertIsNone(wochenstunden_konflikt(zeiten))

    def test_ueber_grenze_konflikt(self) -> None:
        zeiten = [_zeit(i, MONTAG, time(6, 0), time(16, 0)) for i in range(5)]  # 50 h
        konflikt = wochenstunden_konflikt(zeiten)
        self.assertIsNotNone(konflikt)
        self.assertEqual(konflikt.art, "wochenstunden")
        self.assertEqual(len(konflikt.schicht_ids), 5)

    def test_genau_grenze_kein_konflikt(self) -> None:
        zeiten = [_zeit(i, MONTAG, time(0, 0), time(8, 0)) for i in range(6)]  # 48 h
        self.assertIsNone(wochenstunden_konflikt(zeiten))

    def test_grenze_konfigurierbar(self) -> None:
        zeiten = [_zeit(0, MONTAG, time(6, 0), time(16, 0))]  # 10 h
        self.assertIsNotNone(wochenstunden_konflikt(zeiten, max_stunden=8))


class PruefeSchichtenTests(TestCase):
    def test_konfliktfreie_woche(self) -> None:
        mo = _zeit(1, MONTAG, time(6, 0), time(14, 0))
        di = _zeit(2, DIENSTAG, time(6, 0), time(14, 0))
        self.assertEqual(pruefe_schichten([mo, di]), [])

    def test_kombiniert_alle_regeln(self) -> None:
        # Doppelbelegung am Montag + 50 h Gesamt -> Überlappung und Wochenstunden.
        a = _zeit(1, MONTAG, time(6, 0), time(20, 0), "A")  # 14 h
        b = _zeit(2, MONTAG, time(10, 0), time(22, 0), "B")  # 12 h, überlappt A
        c = _zeit(3, DIENSTAG, time(8, 0), time(20, 0), "C")  # 12 h
        d = _zeit(4, date(2026, 6, 24), time(8, 0), time(20, 0), "D")  # 12 h
        arten = {k.art for k in pruefe_schichten([a, b, c, d])}
        self.assertIn("ueberlappung", arten)
        self.assertIn("wochenstunden", arten)

    def test_default_grenzwerte_entsprechen_arbzg(self) -> None:
        self.assertEqual(MIN_RUHEZEIT_STUNDEN, 11.0)
        self.assertEqual(MAX_WOCHENSTUNDEN, 48.0)


class WochenkonflikteTests(TestCase):
    """Der DB-Wrapper: lädt die Woche, gruppiert je Mitarbeiter, prüft."""

    def setUp(self) -> None:
        self.betrieb = BetriebFactory()
        self.person = MitarbeiterFactory(betrieb=self.betrieb)
        self.spaet = SchichtvorlageFactory(
            betrieb=self.betrieb, name="Spät", beginn=time(14, 0), ende=time(22, 0)
        )
        self.frueh = SchichtvorlageFactory(
            betrieb=self.betrieb, name="Früh", beginn=time(6, 0), ende=time(14, 0)
        )

    def _einteilen(self, vorlage, tag: date):
        schicht = SchichtFactory(vorlage=vorlage, datum=tag)
        return ZuweisungFactory(schicht=schicht, mitarbeiter=self.person)

    def test_ruhezeitverstoss_ueber_zwei_tage(self) -> None:
        self._einteilen(self.spaet, MONTAG)  # bis Mo 22:00
        self._einteilen(self.frueh, DIENSTAG)  # ab Di 06:00 -> 8 h Pause
        konflikte = wochenkonflikte(self.betrieb, MONTAG, date(2026, 6, 28))
        self.assertIn(self.person.id, konflikte)
        self.assertEqual(konflikte[self.person.id][0].art, "ruhezeit")

    def test_keine_konflikte_kein_eintrag(self) -> None:
        self._einteilen(self.frueh, MONTAG)
        konflikte = wochenkonflikte(self.betrieb, MONTAG, date(2026, 6, 28))
        self.assertEqual(konflikte, {})

    def test_fremder_betrieb_wird_ignoriert(self) -> None:
        fremd = MitarbeiterFactory()  # eigener Betrieb über SubFactory
        vorlage = SchichtvorlageFactory(
            betrieb=fremd.betrieb, name="Spät", beginn=time(14, 0), ende=time(22, 0)
        )
        schicht = SchichtFactory(vorlage=vorlage, datum=MONTAG)
        ZuweisungFactory(schicht=schicht, mitarbeiter=fremd)
        schicht2 = SchichtFactory(
            vorlage=SchichtvorlageFactory(
                betrieb=fremd.betrieb, name="Früh", beginn=time(6, 0), ende=time(14, 0)
            ),
            datum=DIENSTAG,
        )
        ZuweisungFactory(schicht=schicht2, mitarbeiter=fremd)
        # Aus Sicht von self.betrieb darf nichts auftauchen.
        self.assertEqual(wochenkonflikte(self.betrieb, MONTAG, date(2026, 6, 28)), {})
