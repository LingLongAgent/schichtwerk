"""Verknüpfung zwischen Login und Betrieb.

Bis M10 arbeitete der Prototyp einmandantig: Alle Ansichten bezogen sich auf den
zuerst angelegten ``Betrieb`` (siehe ``planning.services.aktueller_betrieb``). Mit
der Registrierung legt nun jedes Login genau einen eigenen Betrieb an. Diese
Tabelle hält fest, welcher Betrieb zu welchem Login gehört, damit ein angemeldeter
Nutzer seinen — und nicht irgendeinen — Betrieb plant.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from planning.models import Betrieb


class Betriebszugehoerigkeit(models.Model):
    """Ordnet ein Login (User) genau einem Betrieb zu (einmandantig je Login)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="zugehoerigkeit",
        verbose_name="Benutzer",
    )
    betrieb = models.ForeignKey(
        Betrieb,
        on_delete=models.CASCADE,
        related_name="mitglieder",
        verbose_name="Betrieb",
    )
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Betriebszugehörigkeit"
        verbose_name_plural = "Betriebszugehörigkeiten"

    def __str__(self) -> str:
        return f"{self.user.get_username()} → {self.betrieb.name}"
