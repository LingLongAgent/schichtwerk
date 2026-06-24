"""Ansichten der Schichtplanung.

Enthält das (noch wachsende) Dienstplan-Gitter, die Mitarbeiterverwaltung (M2)
sowie die Schichtvorlagen (M3) — jeweils Liste, Detail, Anlegen und Bearbeiten
auf dem Produktions-Design.
"""

from __future__ import annotations

import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import AbteilungForm, AbwesenheitForm, MitarbeiterForm, SchichtvorlageForm
from .models import Abteilung, Abwesenheit, Mitarbeiter, Schichtvorlage, Zuweisung
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
    betrieb = aktueller_betrieb(request.user)
    heute = timezone.localdate()
    start = services.parse_wochenstart(request.GET.get("start"), heute)
    abteilung = services.abteilung_filter(betrieb, request.GET.get("abteilung"))
    gitter = services.wochengitter(betrieb, start, heute, abteilung)
    return render(
        request,
        "planning/schedule.html",
        {
            "gitter": gitter,
            "heute": heute,
            "abteilungen": betrieb.abteilungen.all(),
            "aktive_abteilung": abteilung,
        },
    )


@login_required
def einteilen_tag(request: HttpRequest, pk: int, datum: str) -> HttpResponse:
    """Einteilen-Seite: einen Mitarbeiter an einem Tag Schichten zuweisen/entfernen."""
    betrieb = aktueller_betrieb(request.user)
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
    betrieb = aktueller_betrieb(request.user)
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
    betrieb = aktueller_betrieb(request.user)
    zuweisung = get_object_or_404(Zuweisung, pk=pk, mitarbeiter__betrieb=betrieb)
    person = zuweisung.mitarbeiter
    tag = zuweisung.schicht.datum
    name = zuweisung.schicht.vorlage.name
    zuweisung.delete()
    messages.success(request, f"Einteilung „{name}“ entfernt.")
    return redirect("planning:einteilen_tag", pk=person.pk, datum=tag.isoformat())


@login_required
def stundenuebersicht(request: HttpRequest) -> HttpResponse:
    """Stundenübersicht — geplante Stunden je Mitarbeiter und Tag gegen den Vertrag.

    Die Woche kommt wie beim Dienstplan aus dem Query-Parameter ``start``; ohne ihn
    die laufende Woche. Die Aufbereitung liegt in ``services.stundenuebersicht``
    (ohne HTTP testbar). Von hier aus lässt sich der Plan derselben Woche als CSV
    exportieren (M11).
    """
    betrieb = aktueller_betrieb(request.user)
    heute = timezone.localdate()
    start = services.parse_wochenstart(request.GET.get("start"), heute)
    daten = services.stundenuebersicht(betrieb, start, heute)
    return render(request, "planning/stunden.html", {"daten": daten, "heute": heute})


@login_required
def plan_export(request: HttpRequest) -> HttpResponse:
    """Den Wochenplan als CSV-Datei ausliefern (M11).

    Erzeugt eine semikolon-getrennte CSV mit deutschen Dezimalkommas und einer
    UTF-8-BOM, damit Excel (DE) Umlaute und Spalten direkt korrekt öffnet. Die
    Datenzeilen stammen aus ``services.plan_export_zeilen``; die Woche steuert der
    ``start``-Parameter. Der Dateiname trägt den Wochen-Montag.
    """
    betrieb = aktueller_betrieb(request.user)
    heute = timezone.localdate()
    start = services.parse_wochenstart(request.GET.get("start"), heute)

    antwort = HttpResponse(content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = (
        f'attachment; filename="dienstplan_{start.isoformat()}.csv"'
    )
    antwort.write("﻿")  # BOM, damit Excel die UTF-8-Umlaute korrekt erkennt
    schreiber = csv.writer(antwort, delimiter=";")
    schreiber.writerow(services.PLAN_EXPORT_KOPF)
    schreiber.writerows(services.plan_export_zeilen(betrieb, start))
    return antwort


@login_required
def mitarbeiter_liste(request: HttpRequest) -> HttpResponse:
    """Alle Mitarbeiter des aktiven Betriebs als Tabelle."""
    betrieb = aktueller_betrieb(request.user)
    mitarbeiter = betrieb.mitarbeiter.select_related("abteilung").all()
    return render(
        request,
        "planning/mitarbeiter_liste.html",
        {"mitarbeiter_liste": mitarbeiter},
    )


@login_required
def mitarbeiter_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Einzelansicht eines Mitarbeiters mit Stammdaten und Abwesenheiten."""
    betrieb = aktueller_betrieb(request.user)
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
    betrieb = aktueller_betrieb(request.user)
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
    betrieb = aktueller_betrieb(request.user)
    abwesenheit = get_object_or_404(Abwesenheit, pk=pk, mitarbeiter__betrieb=betrieb)
    person = abwesenheit.mitarbeiter
    abwesenheit.delete()
    messages.success(request, "Abwesenheit entfernt.")
    return redirect("planning:mitarbeiter_detail", pk=person.pk)


@login_required
def mitarbeiter_neu(request: HttpRequest) -> HttpResponse:
    """Neuen Mitarbeiter anlegen."""
    betrieb = aktueller_betrieb(request.user)
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
    betrieb = aktueller_betrieb(request.user)
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
    betrieb = aktueller_betrieb(request.user)
    vorlagen = betrieb.schichtvorlagen.select_related("abteilung").all()
    return render(request, "planning/vorlage_liste.html", {"vorlagen": vorlagen})


@login_required
def vorlage_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Einzelansicht einer Schichtvorlage mit Zeitfenster und Dauer."""
    betrieb = aktueller_betrieb(request.user)
    vorlage = get_object_or_404(Schichtvorlage, pk=pk, betrieb=betrieb)
    return render(request, "planning/vorlage_detail.html", {"vorlage": vorlage})


@login_required
def vorlage_neu(request: HttpRequest) -> HttpResponse:
    """Neue Schichtvorlage anlegen."""
    betrieb = aktueller_betrieb(request.user)
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
    betrieb = aktueller_betrieb(request.user)
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
    betrieb = aktueller_betrieb(request.user)
    vorlage = get_object_or_404(Schichtvorlage, pk=pk, betrieb=betrieb)
    name = vorlage.name
    vorlage.delete()
    messages.success(request, f"Vorlage „{name}“ wurde gelöscht.")
    return redirect("planning:vorlage_liste")


@login_required
def abteilung_liste(request: HttpRequest) -> HttpResponse:
    """Alle Abteilungen des aktiven Betriebs mit Anzahl Mitarbeiter und Vorlagen."""
    betrieb = aktueller_betrieb(request.user)
    abteilungen = betrieb.abteilungen.annotate(
        anzahl_mitarbeiter=Count("mitarbeiter", distinct=True),
        anzahl_vorlagen=Count("schichtvorlagen", distinct=True),
    )
    return render(request, "planning/abteilung_liste.html", {"abteilungen": abteilungen})


@login_required
def abteilung_neu(request: HttpRequest) -> HttpResponse:
    """Neue Abteilung anlegen."""
    betrieb = aktueller_betrieb(request.user)
    if request.method == "POST":
        form = AbteilungForm(request.POST, betrieb=betrieb)
        if form.is_valid():
            abteilung = form.save()
            messages.success(request, f"Abteilung „{abteilung.name}“ wurde angelegt.")
            return redirect("planning:abteilung_liste")
    else:
        form = AbteilungForm(betrieb=betrieb)
    return render(request, "planning/abteilung_form.html", {"form": form, "ist_neu": True})


@login_required
def abteilung_bearbeiten(request: HttpRequest, pk: int) -> HttpResponse:
    """Eine bestehende Abteilung umbenennen."""
    betrieb = aktueller_betrieb(request.user)
    abteilung = get_object_or_404(Abteilung, pk=pk, betrieb=betrieb)
    if request.method == "POST":
        form = AbteilungForm(request.POST, instance=abteilung, betrieb=betrieb)
        if form.is_valid():
            form.save()
            messages.success(request, f"Abteilung „{abteilung.name}“ wurde aktualisiert.")
            return redirect("planning:abteilung_liste")
    else:
        form = AbteilungForm(instance=abteilung, betrieb=betrieb)
    return render(
        request,
        "planning/abteilung_form.html",
        {"form": form, "abteilung": abteilung, "ist_neu": False},
    )


@login_required
@require_POST
def abteilung_loeschen(request: HttpRequest, pk: int) -> HttpResponse:
    """Eine Abteilung löschen (nur per POST von der Liste aus).

    Mitarbeiter und Schichtvorlagen behalten ihre Daten; ihr Abteilungs-Bezug
    wird laut Modell auf ``NULL`` gesetzt (``on_delete=SET_NULL``), sodass kein
    Personal oder Zeitschema verloren geht.
    """
    betrieb = aktueller_betrieb(request.user)
    abteilung = get_object_or_404(Abteilung, pk=pk, betrieb=betrieb)
    name = abteilung.name
    abteilung.delete()
    messages.success(request, f"Abteilung „{name}“ wurde gelöscht.")
    return redirect("planning:abteilung_liste")


@login_required
def onboarding(request: HttpRequest) -> HttpResponse:
    """Geführte Ersteinrichtung: zeigt die offenen Schritte bis zum ersten Plan.

    Ziel der Seite direkt nach der Registrierung: dem frischen Betrieb den Weg zum
    nutzbaren Dienstplan vorgeben (Mitarbeiter → Vorlage → Einteilen). Der
    Fortschritt kommt aus ``services.onboarding_status`` und aktualisiert sich,
    sobald die jeweiligen Daten existieren.
    """
    betrieb = aktueller_betrieb(request.user)
    status = services.onboarding_status(betrieb)
    return render(request, "planning/onboarding.html", {"status": status})
