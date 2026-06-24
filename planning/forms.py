"""Formulare der Schichtplanung.

Die Formulare binden das Datenmodell an die Eingabemasken. Auswahlfelder mit
Bezug zum Mandanten (z. B. die Abteilung) werden bewusst auf den jeweiligen
Betrieb eingeschränkt, damit man keine fremden Datensätze auswählen kann.
"""

from __future__ import annotations

from django import forms

from .models import Abteilung, Betrieb, Mitarbeiter


class MitarbeiterForm(forms.ModelForm):
    """Anlegen/Bearbeiten eines Mitarbeiters innerhalb eines Betriebs.

    ``betrieb`` wird nicht im Formular angezeigt, sondern beim Speichern gesetzt;
    er begrenzt zugleich die wählbaren Abteilungen auf diesen Betrieb.
    """

    class Meta:
        model = Mitarbeiter
        fields = ["vorname", "nachname", "rolle", "abteilung", "vertragsstunden", "farbe", "aktiv"]
        widgets = {"farbe": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args: object, betrieb: Betrieb, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.betrieb = betrieb
        self.fields["abteilung"].queryset = Abteilung.objects.filter(betrieb=betrieb)
        self.fields["abteilung"].empty_label = "— keine —"
        self.fields["rolle"].widget.attrs["placeholder"] = "z. B. Fachkraft"

    def save(self, commit: bool = True) -> Mitarbeiter:
        mitarbeiter: Mitarbeiter = super().save(commit=False)
        mitarbeiter.betrieb = self.betrieb
        if commit:
            mitarbeiter.save()
        return mitarbeiter
