from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from planning import services
from planning.services import aktueller_betrieb


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """Übersicht der laufenden Woche: Kennzahlen, Stunden je Mitarbeiter, Besetzung.

    Die eigentliche Aufbereitung liegt in ``services.dashboard_daten`` (ohne HTTP
    testbar); die View liefert nur den Mandanten- und Wochenkontext und reicht das
    Ergebnis an das Template weiter.
    """
    betrieb = aktueller_betrieb()
    heute = timezone.localdate()
    start = services.wochenstart(heute)
    daten = services.dashboard_daten(betrieb, start, heute)
    return render(request, "pages/dashboard.html", {"daten": daten, "heute": heute})
