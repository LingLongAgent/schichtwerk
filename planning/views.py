"""Ansichten der Schichtplanung.

Enthält das (noch wachsende) Dienstplan-Gitter, die Mitarbeiterverwaltung (M2)
sowie die Schichtvorlagen (M3) — jeweils Liste, Detail, Anlegen und Bearbeiten
auf dem Produktions-Design.
"""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import AbwesenheitForm, MitarbeiterForm, SchichtvorlageForm
from .models import Abwesenheit, Mitarbeiter, Schichtvorlage, Zuweisung
from .services import EinteilenBlockiert, aktueller_betrieb


def _datum_aus_pfad(roh: str) -> date:
    """Ein ISO-Datum aus dem URL-Pfad lesen; bei Unsinn eine 404 auslösen.

    Anders als bei der Wochen-Navigation (die still auf die aktuelle Woche
    zurückfällt) ist ein kaputtes Datum hier ein echter „nicht gefunden"-Fall:
    Die Einteilen-Seite bezieht sich auf genau einen Tag.
    """
    try:
        return date.fromisoformat(roh)
    except ValueError as fehler:
        raise Http404("Ungültiges Datum.") from fehler


@login_required
def schedule(request: HttpRequest) -> HttpResponse:
    """Dienstplan-Wochengitter — Mitarbeiter × Wochentage mit Wochen-Navigation.

    Die anzuzeigende Woche kommt aus dem Query-Parameter ``start`` (ISO-Datum);
    ohne ihn wird die laufende Woche gezeigt. Aus jeder Zelle führt ein Link zum
    Einteilen (M5); offene Schichten erscheinen in einer eigenen Tagesspur.
    """
    betrieb = aktueller_betrieb()
    heute = timezone.localdate()
    start = services.parse_wochenstart(request.GET.get("start"), heute)
    gitter = services.wochengitter(betrieb, start, heute)
    return render(request, "planning/schedule.html", {"gitter": gitter, "heute": heute})


@login_required
def einteilen_tag(request: HttpRequest, pk: int, datum: str) -> HttpResponse:
    """Einteilen-Seite: einen Mitarbeiter an einem Tag Schichten zuweisen/entfernen."""
    betrieb = aktueller_betrieb()
    person = get_object_or_404(Mitarbeiter, pk=pk, betrieb=betrieb)
    tag = _datum_aus_pfad(datum)
    daten = services.tageszuteilung(betrieb, person, tag)
    return render(
        request,
        "planning/einteilen.html",
        {
            "person": person,
            "tag": tag,
            "wochenstart": services.wochenstart(tag),
            "zuweisungen": daten["zuweisungen"],
            "verfuegbar": daten["verfuegbar"],
            "abwesenheit": services.ist_abwesend(person, tag),
        },
    )


@login_required
@require_POST
def einteilung_hinzufuegen(request: HttpRequest, pk: int, datum: str) -> HttpResponse:
    """Den Mitarbeiter der gewählten Vorlage am Tag zuweisen (Schicht entsteht dabei)."""
    betrieb = aktueller_betrieb()
    person = get_object_or_404(Mitarbeiter, pk=pk, betrieb=betrieb)
    tag = _datum_aus_pfad(datum)
    vorlage = get_object_or_404(Schichtvorlage, pk=request.POST.get("vorlage"), betrieb=betrieb)
    try:
        services.einteilen(person, vorlage, tag)
    except EinteilenBlockiert as blockiert:
        messages.error(request, str(blockiert))
    else:
        messages.success(
            request, f"{person.voller_name} für „{vorlage.name}“ am {tag:%d.%m.%Y} eingeteilt."
        )
    return redirect("planning:einteilen_tag", pk=person.pk, datum=tag.isoformat())


@login_required
@require_POST
def einteilung_entfernen(request: HttpRequest, pk: int) -> HttpResponse:
    """Eine Zuweisung wieder entfernen; zurück zur Einteilen-Seite des Tages."""
    betrieb = aktueller_betrieb()
    zuweisung = get_object_or_404(Zuweisung, pk=pk, mitarbeiter__betrieb=betrieb)
    person = zuweisung.mitarbeiter
    tag = zuweisung.schicht.datum
    name = zuweisung.schicht.vorlage.name
    zuweisung.delete()
    messages.success(request, f"Einteilung „{name}“ entfernt.")
    return redirect("planning:einteilen_tag", pk=person.pk, datum=tag.isoformat())


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
    """Einzelansicht eines Mitarbeiters mit Stammdaten und Abwesenheiten."""
    betrieb = aktueller_betrieb()
    person = get_object_or_404(Mitarbeiter, pk=pk, betrieb=betrieb)
    return render(
        request,
        "planning/mitarbeiter_detail.html",
        {
            "person": person,
            "abwesenheiten": person.abwesenheiten.all(),
            "abwesenheit_form": AbwesenheitForm(mitarbeiter=person),
        },
    )


@login_required
@require_POST
def abwesenheit_hinzufuegen(request: HttpRequest, pk: int) -> HttpResponse:
    """Eine Abwesenheit (Urlaub/Krank) für den Mitarbeiter erfassen."""
    betrieb = aktueller_betrieb()
    person = get_object_or_404(Mitarbeiter, pk=pk, betrieb=betrieb)
    form = AbwesenheitForm(request.POST, mitarbeiter=person)
    if form.is_valid():
        form.save()
        messages.success(request, f"Abwesenheit für {person.voller_name} eingetragen.")
        return redirect("planning:mitarbeiter_detail", pk=person.pk)
    # Bei ungültiger Eingabe die Detailseite mit Fehlermeldungen erneut zeigen.
    return render(
        request,
        "planning/mitarbeiter_detail.html",
        {
            "person": person,
            "abwesenheiten": person.abwesenheiten.all(),
            "abwesenheit_form": form,
        },
    )


@login_required
@require_POST
def abwesenheit_entfernen(request: HttpRequest, pk: int) -> HttpResponse:
    """Eine Abwesenheit wieder löschen; zurück zur Mitarbeiter-Detailseite."""
    betrieb = aktueller_betrieb()
    abwesenheit = get_object_or_404(Abwesenheit, pk=pk, mitarbeiter__betrieb=betrieb)
    person = abwesenheit.mitarbeiter
    abwesenheit.delete()
    messages.success(request, "Abwesenheit entfernt.")
    return redirect("planning:mitarbeiter_detail", pk=person.pk)


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
