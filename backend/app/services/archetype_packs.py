"""Canonical, versioned research focus packs.

The registry is deliberately deterministic: it describes which questions a
company profile must cover, while the research artifact still owns the sourced
answer (or an explicit gap).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FocusMarker:
    id: str
    label: str


@dataclass(frozen=True)
class ArchetypePack:
    id: str
    version: str
    label: str
    required_markers: tuple[FocusMarker, ...]


def _markers(*items: tuple[str, str]) -> tuple[FocusMarker, ...]:
    return tuple(FocusMarker(id=key, label=label) for key, label in items)


PACKS: dict[str, ArchetypePack] = {
    "industrial-consumer": ArchetypePack(
        "industrial-consumer",
        "industrial-consumer-v1",
        "Przemysł i konsument",
        _markers(
            ("volume", "Wolumen"),
            ("price_mix", "Cena i miks"),
            ("gross_margin", "Marża brutto"),
            ("fixed_costs", "Koszty stałe"),
            ("backlog", "Portfel zamówień"),
            ("working_capital", "Kapitał obrotowy"),
            ("capex", "Nakłady inwestycyjne"),
        ),
    ),
    "bank-financial": ArchetypePack(
        "bank-financial",
        "bank-financial-v1",
        "Bank i finanse",
        _markers(
            ("loan_deposit_volume", "Wolumen kredytów i depozytów"),
            ("nim", "Marża odsetkowa netto"),
            ("fees", "Wynik prowizyjny"),
            ("cost_of_risk", "Koszt ryzyka"),
            ("capital", "Kapitał i wymogi regulacyjne"),
            ("roe", "ROE"),
        ),
    ),
    "developer-real-estate": ArchetypePack(
        "developer-real-estate",
        "developer-real-estate-v1",
        "Deweloper i nieruchomości",
        _markers(
            ("presales", "Przedsprzedaż"),
            ("handovers", "Przekazania"),
            ("asp", "Średnia cena sprzedaży"),
            ("land_bank", "Bank ziemi"),
            ("nav", "Wartość aktywów netto"),
            ("net_debt", "Dług netto"),
        ),
    ),
    "software-services": ArchetypePack(
        "software-services",
        "software-services-v1",
        "Oprogramowanie i usługi",
        _markers(
            ("recurring_revenue", "Przychody powtarzalne"),
            ("retention", "Utrzymanie klientów"),
            ("utilization", "Wykorzystanie zespołu"),
            ("wages", "Koszty wynagrodzeń"),
            ("cash_conversion", "Konwersja wyniku na gotówkę"),
        ),
    ),
    "gaming-event": ArchetypePack(
        "gaming-event",
        "gaming-event-v1",
        "Gaming i zdarzenia",
        _markers(
            ("launch_timing", "Termin premiery"),
            ("units", "Wolumen sprzedaży"),
            ("price", "Cena"),
            ("platform_share", "Udział platform"),
            ("pipeline", "Pipeline projektów"),
            ("runway", "Runway finansowy"),
        ),
    ),
    "energy-resources": ArchetypePack(
        "energy-resources",
        "energy-resources-v1",
        "Energia i surowce",
        _markers(
            ("volume", "Wolumen"),
            ("commodity_spread", "Cena surowca i spread"),
            ("availability", "Dostępność aktywów"),
            ("unit_costs", "Koszty jednostkowe"),
            ("capex", "Nakłady inwestycyjne"),
            ("debt", "Zadłużenie"),
        ),
    ),
    "holding-biotech": ArchetypePack(
        "holding-biotech",
        "holding-biotech-v1",
        "Holding i biotechnologia",
        _markers(
            ("asset_value", "Wartość aktywów"),
            ("runway", "Runway finansowy"),
            ("milestones", "Kamienie milowe"),
            ("dilution", "Ryzyko rozwodnienia"),
            ("risk_adjusted_value", "Wartość skorygowana o ryzyko"),
        ),
    ),
}

# One already-saved pilot used this provisional version name. It is accepted
# solely when rendering stored data, never as a version for a new profile.
READ_VERSION_ALIASES = {
    ("software-services", "software-services-v1-provisional"): "software-services-v1"
}


def get_pack(archetype: str) -> ArchetypePack | None:
    return PACKS.get(archetype)


def resolve_stored_pack(archetype: str, version: str) -> ArchetypePack | None:
    pack = get_pack(archetype)
    if pack is None:
        return None
    canonical = READ_VERSION_ALIASES.get((archetype, version), version)
    return pack if canonical == pack.version else None


def known_marker_ids(pack: ArchetypePack) -> set[str]:
    return {marker.id for marker in pack.required_markers}


def pack_payload(pack: ArchetypePack) -> dict:
    return {
        "id": pack.id,
        "version": pack.version,
        "label": pack.label,
        "required_markers": [
            {"id": marker.id, "label": marker.label}
            for marker in pack.required_markers
        ],
    }


def evidence_focus_tags(profile: object) -> set[str]:
    tags: set[str] = set()
    for item in [*getattr(profile, "drivers"), *getattr(profile, "kpis")]:
        tags.update(getattr(item, "focus_tags", []))
    return tags


def gap_focus_tags(gaps: list[object]) -> set[str]:
    tags: set[str] = set()
    for item in gaps:
        tags.update(getattr(item, "focus_tags", []))
    return tags


def explicit_focus_tags(profile: object, gaps: list[object]) -> set[str]:
    return evidence_focus_tags(profile) | gap_focus_tags(gaps)


def stored_focus_tags(profile: object, gaps: list[object]) -> tuple[set[str], set[str]]:
    """Read-only best effort for pre-focus-tag JSON artifacts.

    Only exact driver/KPI keys and exact gap topics are inferred. Free text is
    never searched because that would overstate coverage.
    """
    evidence = evidence_focus_tags(profile)
    gap = gap_focus_tags(gaps)
    if evidence or gap:
        return evidence, gap
    pack = resolve_stored_pack(profile.archetype, profile.archetype_version)
    if pack is None:
        return set(), set()
    allowed = known_marker_ids(pack)
    keys = {
        str(getattr(item, "key", ""))
        for item in [*getattr(profile, "drivers"), *getattr(profile, "kpis")]
    }
    topics = {str(getattr(item, "topic", "")) for item in gaps}
    return keys & allowed, topics & allowed


def coverage_payload(profile: object, gaps: list[object]) -> dict | None:
    pack = resolve_stored_pack(profile.archetype, profile.archetype_version)
    if pack is None:
        return None
    allowed = known_marker_ids(pack)
    evidence, gap = stored_focus_tags(profile, gaps)
    evidence &= allowed
    gap &= allowed
    # For legacy pre-focus profiles, an explicit gap is a stronger statement
    # than inferred key coverage. New v2 writes reject such overlap entirely.
    evidence -= gap
    sourced: set[str] = set()
    assumption: set[str] = set()
    for item in [*getattr(profile, "drivers"), *getattr(profile, "kpis")]:
        tags = set(getattr(item, "focus_tags", []))
        if not tags:
            tags = {str(getattr(item, "key", ""))}
        for marker in tags & evidence:
            if getattr(item, "source_document_version_ids", []):
                sourced.add(marker)
            else:
                assumption.add(marker)
    assumption -= sourced
    addressed = sourced | assumption | gap
    required = [marker.id for marker in pack.required_markers]
    count = len(addressed)
    return {
        "id": pack.id,
        "version": pack.version,
        "label": pack.label,
        "required_markers": [
            {
                "id": marker.id,
                "label": marker.label,
                "covered": marker.id in sourced,
                "state": (
                    "sourced"
                    if marker.id in sourced
                    else "assumption"
                    if marker.id in assumption
                    else "gap" if marker.id in gap else "missing"
                ),
            }
            for marker in pack.required_markers
        ],
        "covered_markers": [marker for marker in required if marker in sourced],
        "sourced_markers": [marker for marker in required if marker in sourced],
        "assumption_markers": [marker for marker in required if marker in assumption],
        "gap_markers": [marker for marker in required if marker in gap],
        "missing_markers": [marker for marker in required if marker not in addressed],
        "sourced_count": len(sourced),
        "assumption_count": len(assumption),
        "gap_count": len(gap),
        "missing_count": len(set(required) - addressed),
        "coverage_count": count,
        "coverage_pct": round((count / len(required)) * 100, 1) if required else 100.0,
    }
