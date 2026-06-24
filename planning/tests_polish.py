"""Tests für M12-Politur: konsistente, niveau-gerechte Flash-Meldungen.

Bis M11 erhielten alle Flash-Meldungen dieselbe (neutrale) Optik — eine
Erfolgs- und eine Fehlermeldung sahen gleich aus. M12 macht die Meldung
niveau-gerecht: Das Template hängt die Django-Message-Tags als CSS-Klasse an
(``flash-success`` / ``flash-error``). Hier wird geprüft, dass eine erfolgreiche
Aktion tatsächlich als Erfolg und eine blockierte Aktion als Fehler markiert ist.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .factories import (
    AbwesenheitFactory,
    BetriebFactory,
    MitarbeiterFactory,
    SchichtvorlageFactory,
)


class FlashNiveauTests(TestCase):
    def setUp(self) -> None:
        self.betrieb = BetriebFactory(name="Aktiv-Betrieb")
        self.user = get_user_model().objects.create_user("planer", password="geheim123")
        self.client.force_login(self.user)

    def test_erfolg_meldung_traegt_success_klasse(self) -> None:
        antwort = self.client.post(
            reverse("planning:mitarbeiter_neu"),
            {
                "vorname": "Anna",
                "nachname": "Berg",
                "vertragsstunden": "40",
                "farbe": "#2563eb",
            },
            follow=True,
        )
        self.assertContains(antwort, "flash-success")

    def test_fehler_meldung_traegt_error_klasse(self) -> None:
        # Eine Einteilung an einem Abwesenheitstag wird blockiert -> Fehlermeldung.
        person = MitarbeiterFactory(betrieb=self.betrieb)
        vorlage = SchichtvorlageFactory(betrieb=self.betrieb)
        tag = date(2026, 6, 24)
        AbwesenheitFactory(mitarbeiter=person, von=tag, bis=tag)
        antwort = self.client.post(
            reverse(
                "planning:einteilung_hinzufuegen",
                args=[person.pk, tag.isoformat()],
            ),
            {"vorlage": vorlage.pk},
            follow=True,
        )
        self.assertContains(antwort, "flash-error")

    def test_basis_flash_klasse_bleibt_erhalten(self) -> None:
        # Auch eine niveau-spezifische Meldung trägt weiterhin die Basisklasse.
        antwort = self.client.post(
            reverse("planning:mitarbeiter_neu"),
            {
                "vorname": "Bea",
                "nachname": "Klein",
                "vertragsstunden": "40",
                "farbe": "#2563eb",
            },
            follow=True,
        )
        self.assertContains(antwort, 'class="flash flash-success"')
