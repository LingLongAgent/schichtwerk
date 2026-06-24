"""Admin-Registrierung für schnelle Datenpflege und Inspektion im Prototyp."""

from __future__ import annotations

from django.contrib import admin

from .models import (
    Abteilung,
    Abwesenheit,
    Betrieb,
    Mitarbeiter,
    Schicht,
    Schichtvorlage,
    Zuweisung,
)


@admin.register(Betrieb)
class BetriebAdmin(admin.ModelAdmin):
    list_display = ["name", "erstellt_am"]
    search_fields = ["name"]


@admin.register(Abteilung)
class AbteilungAdmin(admin.ModelAdmin):
    list_display = ["name", "betrieb"]
    list_filter = ["betrieb"]
    search_fields = ["name"]


@admin.register(Mitarbeiter)
class MitarbeiterAdmin(admin.ModelAdmin):
    list_display = ["voller_name", "betrieb", "abteilung", "rolle", "vertragsstunden", "aktiv"]
    list_filter = ["betrieb", "abteilung", "aktiv"]
    search_fields = ["vorname", "nachname"]


@admin.register(Schichtvorlage)
class SchichtvorlageAdmin(admin.ModelAdmin):
    list_display = ["name", "betrieb", "abteilung", "beginn", "ende", "benoetigte_rolle"]
    list_filter = ["betrieb", "abteilung"]
    search_fields = ["name"]


@admin.register(Schicht)
class SchichtAdmin(admin.ModelAdmin):
    list_display = ["vorlage", "datum", "bedarf", "anzahl_zugewiesen", "ist_offen"]
    list_filter = ["datum", "vorlage__betrieb"]
    date_hierarchy = "datum"


@admin.register(Zuweisung)
class ZuweisungAdmin(admin.ModelAdmin):
    list_display = ["mitarbeiter", "schicht", "erstellt_am"]
    list_filter = ["schicht__datum"]


@admin.register(Abwesenheit)
class AbwesenheitAdmin(admin.ModelAdmin):
    list_display = ["mitarbeiter", "art", "von", "bis", "tage"]
    list_filter = ["art", "mitarbeiter__betrieb"]
    date_hierarchy = "von"
