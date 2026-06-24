"""Registrierung eines neuen Betriebs samt Login.

Der Einstieg in den Prototyp: Wer noch keinen Zugang hat, legt hier in einem
Schritt Login und Betrieb an, wird direkt angemeldet und auf das geführte
Onboarding geleitet. Bereits angemeldete Nutzer haben hier nichts zu suchen und
werden auf die Übersicht umgeleitet.
"""

from __future__ import annotations

from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .forms import RegistrierungForm


def registrieren(request: HttpRequest) -> HttpResponse:
    """Neuen Betrieb mit Login anlegen und direkt anmelden."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = RegistrierungForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("planning:onboarding")
    else:
        form = RegistrierungForm()
    return render(request, "accounts/registrieren.html", {"form": form})
