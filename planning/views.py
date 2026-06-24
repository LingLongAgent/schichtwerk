from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def schedule(request):
    """Dienstplan-Gitter — Mitarbeiter auf Schichten einteilen (Build-Loop baut es aus)."""
    return render(request, "planning/schedule.html", {})
