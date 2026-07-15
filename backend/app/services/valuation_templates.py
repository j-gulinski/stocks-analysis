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
        id="industrial-consumer-expectations-v3",
        version="industrial-consumer-template-v3",
        archetype="industrial-consumer",
        label="Konsensus → wariant → wycena wielometodowa",
        driver_copy=(
            "Wolumen i cena/miks budują przychód.",
            "Marża brutto i koszty operacyjne budują EBIT.",
            "FCFF, kapitał obrotowy i capex wpływają bezpośrednio na wartość.",
            "Każdy wzrost i zmiana marży muszą sumować się z nazwanych, źródłowych driverów.",
            "C/Z i EV są metodami względnymi; DCF pozostaje niezależnym sprawdzeniem.",
        ),
        equation="frozen evidence -> named driver deltas -> revenue / margin / reinvestment path -> recurring EPS / EBITDA / EBIT / FCFF -> price-implied hurdle -> primary method + independent cross-checks -> equity value per share",
    ),
    "software-services": ValuationTemplate(
        id="software-services-expectations-v3",
        version="software-services-template-v3",
        archetype="software-services",
        label="Konsensus → wariant → wycena wielometodowa",
        driver_copy=(
            "Przychód cykliczny i projektowy budują skalę.",
            "Retencja, wykorzystanie i presja płacowa kształtują marżę.",
            "FCFF, kapitał obrotowy i capex wpływają bezpośrednio na wartość.",
            "Każdy wzrost i zmiana marży muszą sumować się z nazwanych, źródłowych driverów.",
            "C/Z i EV są metodami względnymi; DCF pozostaje niezależnym sprawdzeniem.",
        ),
        equation="frozen evidence -> named driver deltas -> revenue / margin / reinvestment path -> recurring EPS / EBITDA / EBIT / FCFF -> price-implied hurdle -> primary method + independent cross-checks -> equity value per share",
    ),
}


def get_template(archetype: str) -> ValuationTemplate | None:
    if archetype == "software-services-v1-provisional":
        archetype = "software-services"
    return _TEMPLATES.get(archetype)
