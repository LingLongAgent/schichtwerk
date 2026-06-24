"""Arbeitszeit-Regeln & Konflikterkennung (M6).

Eine Schichtplanung ist nur dann brauchbar, wenn sie auf Verstöße hinweist,
bevor sie veröffentlicht wird. Drei Regeln decken die häufigsten Fehler der
KMU-Planung ab und orientieren sich am Arbeitszeitgesetz (ArbZG):

* **Überlappung** — derselbe Mitarbeiter ist zur selben Zeit zwei Schichten
  zugewiesen (Doppelbelegung). Das ist physisch unmöglich und fast immer ein
  Versehen beim Einteilen.
* **Ruhezeit** — zwischen dem Ende einer Schicht und dem Beginn der nächsten
  müssen mindestens elf Stunden liegen (ArbZG §5). Gerade bei Spät-→Früh-Folgen
  schnell verletzt.
* **Wochenstunden** — die geleisteten Stunden je Woche dürfen einen Höchstwert
  nicht überschreiten (ArbZG §3: 48 h im Schnitt).

Die Prüfungen sind **reine Funktionen** über einfache ``Schichtzeit``-Werte —
ohne Datenbank, ohne HTTP — und lassen sich dadurch erschöpfend testen. Der
dünne Wrapper ``wochenkonflikte`` lädt die Zuweisungen einer Woche und reicht
sie je Mitarbeiter an die Prüfungen weiter.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from .models import Betrieb, Zuweisung

# Gesetzliche Richtwerte (ArbZG) als Vorgaben; je Aufruf überschreibbar.
MIN_RUHEZEIT_STUNDEN = 11.0
MAX_WOCHENSTUNDEN = 48.0


@dataclass(frozen=True)
class Schichtzeit:
    """Eine konkrete Schicht als Zeitspanne — die Eingabe der Regelprüfung.

    Bewusst entkoppelt vom ORM: ``beginn``/``ende`` sind fertige Zeitpunkte
    (Nachtschichten enden am Folgetag), sodass die Prüflogik nichts über
    Vorlagen oder Mitternacht wissen muss.
    """

    schicht_id: int
    name: str
    beginn: datetime
    ende: datetime

    @property
    def dauer_stunden(self) -> float:
        return (self.ende - self.beginn).total_seconds() / 3600


@dataclass(frozen=True)
class Konflikt:
    """Ein erkannter Regelverstoß mit Klartext und den betroffenen Schichten.

    ``art`` erlaubt der Oberfläche eine Gruppierung/Farbgebung; ``schicht_ids``
    nennt die beteiligten Schichten, damit das Gitter die richtigen Zellen
    markieren kann.
    """

    art: str  # "ueberlappung" | "ruhezeit" | "wochenstunden"
    text: str
    schicht_ids: tuple[int, ...]


def _stunden(differenz: datetime, bezug: datetime) -> float:
    return (differenz - bezug).total_seconds() / 3600


def ueberlappungen(zeiten: list[Schichtzeit]) -> list[Konflikt]:
    """Paare zeitlich überlappender Schichten finden (Doppelbelegung).

    Zwei Spannen überlappen, wenn jede vor dem Ende der anderen beginnt. Geprüft
    wird paarweise auf der nach Beginn sortierten Liste; jedes Paar erzeugt
    höchstens einen Konflikt.
    """
    sortiert = sorted(zeiten, key=lambda z: z.beginn)
    konflikte: list[Konflikt] = []
    for i, erste in enumerate(sortiert):
        for zweite in sortiert[i + 1 :]:
            if zweite.beginn >= erste.ende:
                break  # ab hier beginnt alles nach dem Ende der ersten Schicht
            konflikte.append(
                Konflikt(
                    art="ueberlappung",
                    text=f"Doppelbelegung: „{erste.name}“ und „{zweite.name}“ "
                    f"überschneiden sich am {erste.beginn:%d.%m.%Y}.",
                    schicht_ids=(erste.schicht_id, zweite.schicht_id),
                )
            )
    return konflikte


def ruhezeit_verletzungen(
    zeiten: list[Schichtzeit], min_stunden: float = MIN_RUHEZEIT_STUNDEN
) -> list[Konflikt]:
    """Zu kurze Ruhezeiten zwischen aufeinanderfolgenden Schichten melden.

    Maßgeblich ist der Abstand vom spätesten bisherigen Schichtende zum Beginn
    der nächsten Schicht. Überlappende Schichten (Abstand < 0) werden hier
    übersprungen — sie sind bereits als Doppelbelegung erfasst.
    """
    sortiert = sorted(zeiten, key=lambda z: z.beginn)
    konflikte: list[Konflikt] = []
    vorige = None  # Schicht mit dem spätesten Ende unter den bereits gesehenen
    for aktuelle in sortiert:
        if vorige is not None and aktuelle.beginn >= vorige.ende:
            pause = _stunden(aktuelle.beginn, vorige.ende)
            if pause < min_stunden:
                konflikte.append(
                    Konflikt(
                        art="ruhezeit",
                        text=f"Ruhezeit unter {min_stunden:.0f} h: nur "
                        f"{pause:.1f} h zwischen „{vorige.name}“ und "
                        f"„{aktuelle.name}“.",
                        schicht_ids=(vorige.schicht_id, aktuelle.schicht_id),
                    )
                )
        if vorige is None or aktuelle.ende > vorige.ende:
            vorige = aktuelle
    return konflikte


def wochenstunden_konflikt(
    zeiten: list[Schichtzeit], max_stunden: float = MAX_WOCHENSTUNDEN
) -> Konflikt | None:
    """Einen Konflikt liefern, wenn die Summe der Schichtstunden ``max`` übersteigt."""
    gesamt = sum(zeit.dauer_stunden for zeit in zeiten)
    if gesamt <= max_stunden:
        return None
    return Konflikt(
        art="wochenstunden",
        text=f"Wochenstunden über {max_stunden:.0f} h: {gesamt:.1f} h geplant.",
        schicht_ids=tuple(zeit.schicht_id for zeit in zeiten),
    )


def pruefe_schichten(
    zeiten: list[Schichtzeit],
    min_ruhezeit: float = MIN_RUHEZEIT_STUNDEN,
    max_wochenstunden: float = MAX_WOCHENSTUNDEN,
) -> list[Konflikt]:
    """Alle Regeln auf die Schichten **eines** Mitarbeiters anwenden.

    Reihenfolge: erst Doppelbelegungen, dann Ruhezeit, dann Wochenstunden — so
    erscheinen die gravierendsten Verstöße zuerst.
    """
    konflikte = ueberlappungen(zeiten)
    konflikte += ruhezeit_verletzungen(zeiten, min_ruhezeit)
    stunden = wochenstunden_konflikt(zeiten, max_wochenstunden)
    if stunden is not None:
        konflikte.append(stunden)
    return konflikte


def wochenkonflikte(betrieb: Betrieb, start: date, ende: date) -> dict[int, list[Konflikt]]:
    """Konflikte je Mitarbeiter für das Wochenfenster ``start``–``ende`` ermitteln.

    Lädt alle Zuweisungen der Woche in einer Abfrage, gruppiert sie je
    Mitarbeiter zu ``Schichtzeit``-Werten und wendet die Regeln an. Mitarbeiter
    ohne Verstoß tauchen im Ergebnis nicht auf, damit die Aufrufer nur über
    tatsächliche Konflikte iterieren.
    """
    je_person: dict[int, list[Schichtzeit]] = defaultdict(list)
    zuweisungen = Zuweisung.objects.filter(
        mitarbeiter__betrieb=betrieb,
        schicht__datum__range=(start, ende),
    ).select_related("schicht__vorlage")
    for zuweisung in zuweisungen:
        schicht = zuweisung.schicht
        je_person[zuweisung.mitarbeiter_id].append(
            Schichtzeit(
                schicht_id=schicht.id,
                name=schicht.vorlage.name,
                beginn=schicht.beginn_am,
                ende=schicht.ende_am,
            )
        )

    ergebnis: dict[int, list[Konflikt]] = {}
    for mitarbeiter_id, zeiten in je_person.items():
        konflikte = pruefe_schichten(zeiten)
        if konflikte:
            ergebnis[mitarbeiter_id] = konflikte
    return ergebnis
