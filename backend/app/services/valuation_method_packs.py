"""Versioned valuation lenses; readiness is evidence, never a marketing label."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ValuationMethodPack:
    id: str
    version: str
    label: str
    status: str
    reason: str | None
    skill: str | None

    def to_dict(self) -> dict:
        return asdict(self)


PACKS = (
    ValuationMethodPack(
        id="malik_obs_v1",
        version="malik-obs-valuation-v1",
        label="Paweł Malik / OBS",
        status="ready",
        reason=None,
        skill="strategy-malik-obs",
    ),
    ValuationMethodPack(
        id="areczeks_v1",
        version="areczeks-draft-v1",
        label="Areczeks",
        status="blocked",
        reason="Brak zachowanych, datowanych materiałów źródłowych do wersjonowanego packa.",
        skill=None,
    ),
    ValuationMethodPack(
        id="elendix_v1",
        version="elendix-draft-v1",
        label="Elendix",
        status="blocked",
        reason="Brak pełnego, zachowanego materiału źródłowego i zweryfikowanych reguł wyceny.",
        skill=None,
    ),
)


def list_method_packs() -> list[dict]:
    return [pack.to_dict() for pack in PACKS]


def get_method_pack(pack_id: str) -> ValuationMethodPack | None:
    return next((pack for pack in PACKS if pack.id == pack_id), None)

