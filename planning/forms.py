"""Formulare der Schichtplanung.

Die Formulare binden das Datenmodell an die Eingabemasken. Auswahlfelder mit
Bezug zum Mandanten (z. B. die Abteilung) werden bewusst auf den jeweiligen
Betrieb eingeschränkt, damit man keine fremden Datensätze auswählen kann.
"""

from __future__ import annotations

from django import forms

from .models import Abteilung, Betrieb, Mitarbeiter, Schichtvorlage


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


class SchichtvorlageForm(forms.ModelForm):
    """Anlegen/Bearbeiten einer Schichtvorlage (Früh/Spät/Nacht) eines Betriebs.

    Wie beim Mitarbeiter wird ``betrieb`` beim Speichern gesetzt und begrenzt die
    wählbaren Abteilungen. Ein Ende, das nicht nach dem Beginn liegt, ist bewusst
    erlaubt — so lassen sich Nachtschichten über Mitternacht abbilden; eine
    Vorlage mit identischem Beginn und Ende (Dauer 0) wäre dagegen sinnlos und
    wird abgewiesen.
    """

    class Meta:
        model = Schichtvorlage
        fields = ["name", "abteilung", "beginn", "ende", "benoetigte_rolle", "farbe"]
        widgets = {
            "beginn": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "ende": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "farbe": forms.TextInput(attrs={"type": "color"}),
        }

    def __init__(self, *args: object, betrieb: Betrieb, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.betrieb = betrieb
        self.fields["abteilung"].queryset = Abteilung.objects.filter(betrieb=betrieb)
        self.fields["abteilung"].empty_label = "— keine —"
        self.fields["name"].widget.attrs["placeholder"] = "z. B. Frühschicht"
        self.fields["benoetigte_rolle"].widget.attrs["placeholder"] = "z. B. Fachkraft"

    def clean(self) -> dict[str, object]:
        bereinigt = super().clean()
        beginn = bereinigt.get("beginn")
        ende = bereinigt.get("ende")
        if beginn is not None and ende is not None and beginn == ende:
            raise forms.ValidationError("Beginn und Ende dürfen nicht identisch sein.")
        return bereinigt

    def save(self, commit: bool = True) -> Schichtvorlage:
        vorlage: Schichtvorlage = super().save(commit=False)
        vorlage.betrieb = self.betrieb
        if commit:
            vorlage.save()
        return vorlage
