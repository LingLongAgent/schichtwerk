"""Formulare rund um Registrierung und Onboarding.

Die Registrierung ist der Einstieg in den Prototyp: In einem Schritt entstehen ein
Login und der zugehörige Betrieb. Das Formular erweitert Djangos
``UserCreationForm`` (für die geprüfte Passwortvergabe) um den Betriebsnamen und
eine optionale E-Mail. Das eigentliche Anlegen von User, Betrieb und Zuordnung
passiert gebündelt in ``save`` innerhalb einer Transaktion.
"""

from __future__ import annotations

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from planning.models import Betrieb

from .models import Betriebszugehoerigkeit


class RegistrierungForm(UserCreationForm):
    """Legt in einem Rutsch ein Login samt eigenem Betrieb an."""

    betrieb_name = forms.CharField(label="Name des Betriebs", max_length=120)
    email = forms.EmailField(label="E-Mail", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["betrieb_name", "username", "email"]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["betrieb_name"].widget.attrs["placeholder"] = "z. B. Bäckerei Sonnenschein"
        self.fields["username"].widget.attrs["placeholder"] = "Benutzername"

    @transaction.atomic
    def save(self, commit: bool = True) -> User:
        """User, Betrieb und ihre Zuordnung gemeinsam anlegen.

        ``commit=False`` ergibt für die Registrierung keinen Sinn — der Betrieb
        braucht einen gespeicherten User —, daher wird immer gespeichert.
        """
        user = super().save(commit=True)
        user.email = self.cleaned_data.get("email", "")
        user.save(update_fields=["email"])
        betrieb = Betrieb.objects.create(name=self.cleaned_data["betrieb_name"])
        Betriebszugehoerigkeit.objects.create(user=user, betrieb=betrieb)
        return user
