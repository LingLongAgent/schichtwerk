from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def dashboard(request):
    """Übersicht: Besetzung, offene Schichten, Stunden — gefüllt durch den Build-Loop."""
    kpis = [
        {"label": "Mitarbeiter", "value": 0},
        {"label": "Schichten diese Woche", "value": 0},
        {"label": "Offene Schichten", "value": 0},
        {"label": "Konflikte", "value": 0},
    ]
    return render(request, "pages/dashboard.html", {"kpis": kpis})
