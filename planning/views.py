"""Ansichten der Schichtplanung.

Enthält das (noch wachsende) Dienstplan-Gitter, die Mitarbeiterverwaltung (M2)
sowie die Schichtvorlagen (M3) — jeweils Liste, Detail, Anlegen und Bearbeiten
auf dem Produktions-Design.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import MitarbeiterForm, SchichtvorlageForm
from .models import Mitarbeiter, Schichtvorlage
from .services import aktueller_betrieb


@login_required
def schedule(request: HttpRequest) -> HttpResponse:
    """Dienstplan-Wochengitter — Mitarbeiter × Wochentage mit Wochen-Navigation.

    Die anzuzeigende Woche kommt aus dem Query-Parameter ``start`` (ISO-Datum);
    ohne ihn wird die laufende Woche gezeigt. Das Einteilen selbst folgt in M5.
    """
    betrieb = aktueller_betrieb()
    heute = timezone.localdate()
    start = services.parse_wochenstart(request.GET.get("start"), heute)
    gitter = services.wochengitter(betrieb, start, heute)
    return render(request, "planning/schedule.html", {"gitter": gitter, "heute": heute})


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


@login_required
def vorlage_liste(request: HttpRequest) -> HttpResponse:
    """Alle Schichtvorlagen des aktiven Betriebs als Tabelle."""
    betrieb = aktueller_betrieb()
    vorlagen = betrieb.schichtvorlagen.select_related("abteilung").all()
    return render(request, "planning/vorlage_liste.html", {"vorlagen": vorlagen})


@login_required
def vorlage_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Einzelansicht einer Schichtvorlage mit Zeitfenster und Dauer."""
    betrieb = aktueller_betrieb()
    vorlage = get_object_or_404(Schichtvorlage, pk=pk, betrieb=betrieb)
    return render(request, "planning/vorlage_detail.html", {"vorlage": vorlage})


@login_required
def vorlage_neu(request: HttpRequest) -> HttpResponse:
    """Neue Schichtvorlage anlegen."""
    betrieb = aktueller_betrieb()
    if request.method == "POST":
        form = SchichtvorlageForm(request.POST, betrieb=betrieb)
        if form.is_valid():
            vorlage = form.save()
            messages.success(request, f"Vorlage „{vorlage.name}“ wurde angelegt.")
            return redirect("planning:vorlage_detail", pk=vorlage.pk)
    else:
        form = SchichtvorlageForm(betrieb=betrieb)
    return render(request, "planning/vorlage_form.html", {"form": form, "ist_neu": True})


@login_required
def vorlage_bearbeiten(request: HttpRequest, pk: int) -> HttpResponse:
    """Zeitschema einer bestehenden Schichtvorlage ändern."""
    betrieb = aktueller_betrieb()
    vorlage = get_object_or_404(Schichtvorlage, pk=pk, betrieb=betrieb)
    if request.method == "POST":
        form = SchichtvorlageForm(request.POST, instance=vorlage, betrieb=betrieb)
        if form.is_valid():
            form.save()
            messages.success(request, f"Vorlage „{vorlage.name}“ wurde aktualisiert.")
            return redirect("planning:vorlage_detail", pk=vorlage.pk)
    else:
        form = SchichtvorlageForm(instance=vorlage, betrieb=betrieb)
    return render(
        request,
        "planning/vorlage_form.html",
        {"form": form, "vorlage": vorlage, "ist_neu": False},
    )


@login_required
@require_POST
def vorlage_loeschen(request: HttpRequest, pk: int) -> HttpResponse:
    """Eine Schichtvorlage löschen (nur per POST von der Detailseite aus)."""
    betrieb = aktueller_betrieb()
    vorlage = get_object_or_404(Schichtvorlage, pk=pk, betrieb=betrieb)
    name = vorlage.name
    vorlage.delete()
    messages.success(request, f"Vorlage „{name}“ wurde gelöscht.")
    return redirect("planning:vorlage_liste")
