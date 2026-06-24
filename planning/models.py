"""Datenmodell der Schichtplanung.

Die Domäne bildet ab, wie ein KMU seine Dienste plant: Ein ``Betrieb`` gliedert
sich in ``Abteilung``-en und beschäftigt ``Mitarbeiter``. Wiederkehrende Dienste
(Früh/Spät/Nacht) werden als ``Schichtvorlage`` einmalig definiert und an
konkreten Tagen als ``Schicht`` instanziiert. Eine ``Zuweisung`` verbindet
schließlich einen Mitarbeiter mit einer konkreten Schicht — das ist der Kern,
den das spätere Wochengitter (M4/M5) bearbeitet.

Bewusst getrennt: Vorlage (Zeitschema) vs. Instanz (Schicht an einem Datum).
So lassen sich Zeiten zentral pflegen und Schichten je Tag besetzen.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db import models

# Vorgabe-Farbe für die farbliche Kennzeichnung im Gitter (Tailwind-Blau 600).
STANDARD_FARBE = "#2563eb"


class Betrieb(models.Model):
    """Ein Unternehmen/Standort, der Schichten plant — oberste Mandanten-Ebene."""

    name = models.CharField("Name", max_length=120)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Betrieb"
        verbose_name_plural = "Betriebe"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Abteilung(models.Model):
    """Organisationseinheit innerhalb eines Betriebs (z. B. Küche, Empfang)."""

    betrieb = models.ForeignKey(
        Betrieb, on_delete=models.CASCADE, related_name="abteilungen", verbose_name="Betrieb"
    )
    name = models.CharField("Name", max_length=120)

    class Meta:
        verbose_name = "Abteilung"
        verbose_name_plural = "Abteilungen"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["betrieb", "name"], name="abteilung_name_je_betrieb_eindeutig"
            )
        ]

    def __str__(self) -> str:
        return self.name


class Mitarbeiter(models.Model):
    """Eine beschäftigte Person, die Schichten übernimmt.

    ``vertragsstunden`` ist die wöchentliche Sollarbeitszeit und dient später
    (M6/M11) als Maßstab für Über-/Unterbesetzung. ``farbe`` macht die Person
    im Wochengitter auf einen Blick erkennbar.
    """

    betrieb = models.ForeignKey(
        Betrieb, on_delete=models.CASCADE, related_name="mitarbeiter", verbose_name="Betrieb"
    )
    abteilung = models.ForeignKey(
        Abteilung,
        on_delete=models.SET_NULL,
        related_name="mitarbeiter",
        null=True,
        blank=True,
        verbose_name="Abteilung",
    )
    vorname = models.CharField("Vorname", max_length=80)
    nachname = models.CharField("Nachname", max_length=80)
    rolle = models.CharField("Rolle", max_length=80, blank=True)
    vertragsstunden = models.DecimalField(
        "Vertragsstunden/Woche", max_digits=5, decimal_places=2, default=40
    )
    farbe = models.CharField("Farbe", max_length=7, default=STANDARD_FARBE)
    aktiv = models.BooleanField("Aktiv", default=True)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Mitarbeiter"
        verbose_name_plural = "Mitarbeiter"
        ordering = ["nachname", "vorname"]

    def __str__(self) -> str:
        return self.voller_name

    @property
    def voller_name(self) -> str:
        """Anzeigename ``Vorname Nachname`` für Listen und das Gitter."""
        return f"{self.vorname} {self.nachname}".strip()


class Schichtvorlage(models.Model):
    """Wiederkehrendes Zeitschema eines Dienstes (z. B. Frühschicht 06–14 Uhr).

    Die Vorlage trägt das Zeitfenster und — optional — die fachlich benötigte
    Rolle. Konkrete Tagesschichten verweisen darauf, statt Zeiten zu duplizieren.
    Nachtschichten über Mitternacht werden unterstützt (Ende <= Beginn).
    """

    betrieb = models.ForeignKey(
        Betrieb,
        on_delete=models.CASCADE,
        related_name="schichtvorlagen",
        verbose_name="Betrieb",
    )
    abteilung = models.ForeignKey(
        Abteilung,
        on_delete=models.SET_NULL,
        related_name="schichtvorlagen",
        null=True,
        blank=True,
        verbose_name="Abteilung",
    )
    name = models.CharField("Name", max_length=80)
    beginn = models.TimeField("Beginn")
    ende = models.TimeField("Ende")
    benoetigte_rolle = models.CharField("Benötigte Rolle", max_length=80, blank=True)
    farbe = models.CharField("Farbe", max_length=7, default=STANDARD_FARBE)

    class Meta:
        verbose_name = "Schichtvorlage"
        verbose_name_plural = "Schichtvorlagen"
        ordering = ["beginn", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.beginn:%H:%M}–{self.ende:%H:%M})"

    @property
    def dauer_stunden(self) -> float:
        """Schichtlänge in Stunden; rechnet Nachtschichten über Mitternacht korrekt.

        Liegt das Ende nicht nach dem Beginn, wird von einem Tageswechsel
        ausgegangen und ein voller Tag aufaddiert.
        """
        return _stunden_zwischen(self.beginn, self.ende)


class Schicht(models.Model):
    """Eine konkrete Schicht an einem Datum, abgeleitet aus einer Vorlage.

    ``bedarf`` gibt an, wie viele Mitarbeiter benötigt werden; sind weniger
    zugewiesen, gilt die Schicht als offen (für die Markierung im Gitter, M5).
    """

    vorlage = models.ForeignKey(
        Schichtvorlage,
        on_delete=models.CASCADE,
        related_name="schichten",
        verbose_name="Vorlage",
    )
    datum = models.DateField("Datum")
    bedarf = models.PositiveSmallIntegerField("Benötigte Mitarbeiter", default=1)

    class Meta:
        verbose_name = "Schicht"
        verbose_name_plural = "Schichten"
        ordering = ["datum", "vorlage__beginn"]
        constraints = [
            models.UniqueConstraint(
                fields=["vorlage", "datum"], name="schicht_je_vorlage_und_datum_eindeutig"
            )
        ]

    def __str__(self) -> str:
        return f"{self.vorlage.name} am {self.datum:%d.%m.%Y}"

    @property
    def betrieb(self) -> Betrieb:
        return self.vorlage.betrieb

    @property
    def beginn(self) -> time:
        return self.vorlage.beginn

    @property
    def ende(self) -> time:
        return self.vorlage.ende

    @property
    def dauer_stunden(self) -> float:
        return self.vorlage.dauer_stunden

    @property
    def beginn_am(self) -> datetime:
        """Beginn als konkreter Zeitpunkt (Datum + Uhrzeit der Vorlage)."""
        return datetime.combine(self.datum, self.beginn)

    @property
    def ende_am(self) -> datetime:
        """Ende als konkreter Zeitpunkt; bei Nachtschicht (Ende <= Beginn) am Folgetag.

        Liefert zusammen mit ``beginn_am`` das Zeitfenster, an dem die
        Regelprüfung (Überlappung/Ruhezeit) arbeitet. Wall-clock-Zeiten genügen,
        da nur Differenzen innerhalb derselben lokalen Zeit verglichen werden.
        """
        ende = datetime.combine(self.datum, self.ende)
        if self.ende <= self.beginn:
            ende += timedelta(days=1)
        return ende

    @property
    def anzahl_zugewiesen(self) -> int:
        return self.zuweisungen.count()

    @property
    def ist_offen(self) -> bool:
        """True, wenn die Schicht noch nicht ausreichend besetzt ist."""
        return self.anzahl_zugewiesen < self.bedarf


class Zuweisung(models.Model):
    """Verbindet einen Mitarbeiter mit einer konkreten Schicht (die Einteilung)."""

    schicht = models.ForeignKey(
        Schicht, on_delete=models.CASCADE, related_name="zuweisungen", verbose_name="Schicht"
    )
    mitarbeiter = models.ForeignKey(
        Mitarbeiter,
        on_delete=models.CASCADE,
        related_name="zuweisungen",
        verbose_name="Mitarbeiter",
    )
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Zuweisung"
        verbose_name_plural = "Zuweisungen"
        ordering = ["schicht__datum"]
        constraints = [
            models.UniqueConstraint(
                fields=["schicht", "mitarbeiter"],
                name="mitarbeiter_je_schicht_eindeutig",
            )
        ]

    def __str__(self) -> str:
        return f"{self.mitarbeiter.voller_name} → {self.schicht}"


class Abwesenheit(models.Model):
    """Ein Zeitraum, in dem ein Mitarbeiter nicht einplanbar ist (Urlaub/Krank).

    Der Zeitraum ist **inklusive** zu verstehen: ``von`` und ``bis`` zählen beide
    als abwesend (ein eintägiger Urlaub hat ``von == bis``). Eine Abwesenheit
    blockiert das Einteilen an den betroffenen Tagen (siehe ``services.einteilen``)
    und wird im Wochengitter sichtbar gemacht.
    """

    URLAUB = "urlaub"
    KRANK = "krank"
    SONSTIGES = "sonstiges"
    ART_AUSWAHL = [
        (URLAUB, "Urlaub"),
        (KRANK, "Krank"),
        (SONSTIGES, "Sonstiges"),
    ]

    mitarbeiter = models.ForeignKey(
        Mitarbeiter,
        on_delete=models.CASCADE,
        related_name="abwesenheiten",
        verbose_name="Mitarbeiter",
    )
    art = models.CharField("Art", max_length=20, choices=ART_AUSWAHL, default=URLAUB)
    von = models.DateField("Von")
    bis = models.DateField("Bis")
    notiz = models.CharField("Notiz", max_length=200, blank=True)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Abwesenheit"
        verbose_name_plural = "Abwesenheiten"
        ordering = ["-von"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(bis__gte=models.F("von")),
                name="abwesenheit_bis_nicht_vor_von",
            )
        ]

    def __str__(self) -> str:
        return f"{self.art_anzeige}: {self.von:%d.%m.%Y}–{self.bis:%d.%m.%Y}"

    @property
    def art_anzeige(self) -> str:
        """Lesbarer Name der Abwesenheitsart (z. B. „Urlaub")."""
        return self.get_art_display()

    @property
    def tage(self) -> int:
        """Anzahl der abgedeckten Kalendertage (inklusive Start- und Endtag)."""
        return (self.bis - self.von).days + 1

    def umfasst(self, datum: date) -> bool:
        """True, wenn ``datum`` in den (inklusiven) Abwesenheitszeitraum fällt."""
        return self.von <= datum <= self.bis


def _stunden_zwischen(beginn: time, ende: time) -> float:
    """Stunden zwischen zwei Uhrzeiten; bei Tageswechsel (Ende <= Beginn) +24h.

    Als freie Funktion gehalten, damit Vorlage und Schicht dieselbe Regel teilen
    und die Logik isoliert getestet werden kann.
    """
    basis = datetime(2000, 1, 1, beginn.hour, beginn.minute)
    schluss = datetime(2000, 1, 1, ende.hour, ende.minute)
    if schluss <= basis:
        schluss += timedelta(days=1)
    return (schluss - basis).total_seconds() / 3600
