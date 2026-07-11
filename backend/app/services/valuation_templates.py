"""Archetype-bound valuation calculation templates."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ValuationTemplate:
    id: str
    version: str
    archetype: str
    label: str
    driver_copy: tuple[str, ...]
    equation: str

    def to_dict(self) -> dict:
        value = asdict(self)
        value["driver_copy"] = list(self.driver_copy)
        return value


_TEMPLATES = {
    "industrial-consumer": ValuationTemplate(
        id="industrial-consumer-earnings-pe-v1",
        version="industrial-consumer-template-v1",
        archetype="industrial-consumer",
        label="Wynik operacyjny industrial/consumer + C/Z",
        driver_copy=(
            "Wolumen i cena/miks budują przychód.",
            "Marża brutto i koszty operacyjne budują EBIT.",
            "Konwersja gotówki i capex pokazują jakość wyniku.",
        ),
        equation="revenue -> gross profit -> EBIT -> net result -> EPS; CFO - positive capex spend -> FCF; EPS x target C/Z -> price",
    ),
    "software-services": ValuationTemplate(
        id="software-services-earnings-pe-v1",
        version="software-services-template-v1",
        archetype="software-services",
        label="Wynik operacyjny software/services + C/Z",
        driver_copy=(
            "Przychód cykliczny i projektowy budują skalę.",
            "Retencja, wykorzystanie i presja płacowa kształtują marżę.",
            "Konwersja gotówki oddziela wynik księgowy od gotówki.",
        ),
        equation="revenue -> gross profit -> EBIT -> net result -> EPS; CFO - positive capex spend -> FCF; EPS x target C/Z -> price",
    ),
}


def get_template(archetype: str) -> ValuationTemplate | None:
    if archetype == "software-services-v1-provisional":
        archetype = "software-services"
    return _TEMPLATES.get(archetype)

