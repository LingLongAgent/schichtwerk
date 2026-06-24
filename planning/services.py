"""Kleine Hilfsfunktionen rund um den aktiven Mandanten.

Solange Registrierung/Onboarding (M10) fehlt, arbeitet der Prototyp einmandantig:
Es gibt genau einen ``Betrieb``, auf den sich alle Ansichten beziehen. Diese
Funktion kapselt diese Annahme an einer Stelle, damit M10 sie später ersetzen
kann, ohne dass die Views angefasst werden müssen.
"""

from __future__ import annotations

from .models import Betrieb

STANDARD_BETRIEB_NAME = "Mein Betrieb"


def aktueller_betrieb() -> Betrieb:
    """Liefert den Betrieb, in dessen Kontext gerade geplant wird.

    Existiert noch keiner (frische Installation), wird ein Standard-Betrieb
    angelegt, damit die Ansichten ohne vorheriges Onboarding nutzbar sind.
    """
    betrieb = Betrieb.objects.first()
    if betrieb is None:
        betrieb = Betrieb.objects.create(name=STANDARD_BETRIEB_NAME)
    return betrieb
