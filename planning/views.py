"""Ansichten der Schichtplanung.

Enthält das (noch wachsende) Dienstplan-Gitter sowie die Mitarbeiterverwaltung
(M2): Liste, Detail, Anlegen und Bearbeiten — alle auf dem Produktions-Design.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MitarbeiterForm
from .models import Mitarbeiter
from .services import aktueller_betrieb


@login_required
def schedule(request: HttpRequest) -> HttpResponse:
    """Dienstplan-Gitter — Mitarbeiter auf Schichten einteilen (Build-Loop baut es aus)."""
    return render(request, "planning/schedule.html", {})


@login_required
def mitarbeiter_liste(request: HttpRequest) -> HttpResponse:
    """Alle Mitarbeiter des aktiven Betriebs als Tabelle."""
    betrieb = aktueller_betrieb()
    mitarbeiter = betrieb.mitarbeiter.select_related("abteilung").all()
    return render(
        request,
        "planning/mitarbeiter_liste.html",
        {"mitarbeiter_liste": mitarbeiter},
    )


@login_required
def mitarbeiter_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Einzelansicht eines Mitarbeiters mit Stammdaten."""
    betrieb = aktueller_betrieb()
    person = get_object_or_404(Mitarbeiter, pk=pk, betrieb=betrieb)
    return render(request, "planning/mitarbeiter_detail.html", {"person": person})


@login_required
def mitarbeiter_neu(request: HttpRequest) -> HttpResponse:
    """Neuen Mitarbeiter anlegen."""
    betrieb = aktueller_betrieb()
    if request.method == "POST":
        form = MitarbeiterForm(request.POST, betrieb=betrieb)
        if form.is_valid():
            person = form.save()
            messages.success(request, f"{person.voller_name} wurde angelegt.")
            return redirect("planning:mitarbeiter_detail", pk=person.pk)
    else:
        form = MitarbeiterForm(betrieb=betrieb)
    return render(
        request,
        "planning/mitarbeiter_form.html",
        {"form": form, "ist_neu": True},
    )


@login_required
def mitarbeiter_bearbeiten(request: HttpRequest, pk: int) -> HttpResponse:
    """Stammdaten eines bestehenden Mitarbeiters ändern."""
    betrieb = aktueller_betrieb()
    person = get_object_or_404(Mitarbeiter, pk=pk, betrieb=betrieb)
    if request.method == "POST":
        form = MitarbeiterForm(request.POST, instance=person, betrieb=betrieb)
        if form.is_valid():
            form.save()
            messages.success(request, f"{person.voller_name} wurde aktualisiert.")
            return redirect("planning:mitarbeiter_detail", pk=person.pk)
    else:
        form = MitarbeiterForm(instance=person, betrieb=betrieb)
    return render(
        request,
        "planning/mitarbeiter_form.html",
        {"form": form, "person": person, "ist_neu": False},
    )
