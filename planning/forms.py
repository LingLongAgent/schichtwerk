"""Formulare der Schichtplanung.

Die Formulare binden das Datenmodell an die Eingabemasken. Auswahlfelder mit
Bezug zum Mandanten (z. B. die Abteilung) werden bewusst auf den jeweiligen
Betrieb eingeschränkt, damit man keine fremden Datensätze auswählen kann.
"""

from __future__ import annotations

from django import forms

from .models import Abteilung, Abwesenheit, Betrieb, Mitarbeiter, Schichtvorlage


class AbteilungForm(forms.ModelForm):
    """Anlegen/Bearbeiten einer Abteilung (z. B. Küche, Empfang) eines Betriebs.

    ``betrieb`` wird nicht im Formular gezeigt, sondern beim Speichern gesetzt.
    Der Name muss je Betrieb eindeutig sein (passend zur DB-Bedingung am Modell);
    geprüft wird ohne Rücksicht auf Groß-/Kleinschreibung, damit nicht „Küche"
    und „küche" nebeneinander entstehen. Beim Bearbeiten ist der eigene Datensatz
    von der Prüfung ausgenommen.
    """

    class Meta:
        model = Abteilung
        fields = ["name"]

    def __init__(self, *args: object, betrieb: Betrieb, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.betrieb = betrieb
        self.fields["name"].widget.attrs["placeholder"] = "z. B. Küche"

    def clean_name(self) -> str:
        name: str = self.cleaned_data["name"]
        schon_vergeben = Abteilung.objects.filter(betrieb=self.betrieb, name__iexact=name)
        if self.instance.pk is not None:
            schon_vergeben = schon_vergeben.exclude(pk=self.instance.pk)
        if schon_vergeben.exists():
            raise forms.ValidationError("Eine Abteilung mit diesem Namen existiert bereits.")
        return name

    def save(self, commit: bool = True) -> Abteilung:
        abteilung: Abteilung = super().save(commit=False)
        abteilung.betrieb = self.betrieb
        if commit:
            abteilung.save()
        return abteilung


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


class AbwesenheitForm(forms.ModelForm):
    """Eine Abwesenheit (Urlaub/Krank) für einen Mitarbeiter erfassen.

    Der Mitarbeiter wird nicht im Formular gewählt, sondern beim Speichern aus
    dem Seitenkontext gesetzt. Ein Enddatum vor dem Beginn ist unzulässig und
    wird vor dem Speichern abgewiesen, passend zur DB-Bedingung am Modell.
    """

    class Meta:
        model = Abwesenheit
        fields = ["art", "von", "bis", "notiz"]
        widgets = {
            "von": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "bis": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args: object, mitarbeiter: Mitarbeiter, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.mitarbeiter = mitarbeiter
        self.fields["notiz"].widget.attrs["placeholder"] = "optional"

    def clean(self) -> dict[str, object]:
        bereinigt = super().clean()
        von = bereinigt.get("von")
        bis = bereinigt.get("bis")
        if von is not None and bis is not None and bis < von:
            raise forms.ValidationError("Das Bis-Datum darf nicht vor dem Von-Datum liegen.")
        return bereinigt

    def save(self, commit: bool = True) -> Abwesenheit:
        abwesenheit: Abwesenheit = super().save(commit=False)
        abwesenheit.mitarbeiter = self.mitarbeiter
        if commit:
            abwesenheit.save()
        return abwesenheit
