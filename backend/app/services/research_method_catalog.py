"""Source-frozen, stage-aware catalog of Research method lenses.

The catalog describes what a lens may ask of one immutable Research snapshot.
It does not produce a company conclusion, queue work, or replace a verifier.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class MethodStageReadiness:
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class MethodSource:
    id: str
    label: str
    repo_path: str | None
    sha256: str | None
    author_identity: str | None
    source_url: str | None
    locator: str | None
    publication_at: str | None
    known_at: str | None
    date_note: str | None
    retention_status: str


@dataclass(frozen=True)
class MethodRequiredCheck:
    """One stable question that a method perspective must classify once."""

    id: str
    label: str
    origin: str


@dataclass(frozen=True)
class ResearchMethodCatalogEntry:
    id: str
    version: str
    label: str
    disclaimer: str
    stages: dict[str, MethodStageReadiness]
    evaluation_maturity: str
    skill: str | None
    research_output_schema_version: str | None
    valuation_output_schema_version: str | None
    calculation_engine_version: str | None
    required_verifier_role: str | None
    source_manifest: tuple[MethodSource, ...]
    required_questions: tuple[str, ...]
    required_checks: tuple[MethodRequiredCheck, ...]
    blind_spots: tuple[str, ...]
    gaps: tuple[str, ...]

    def to_dict(self) -> dict:
        value = asdict(self)
        for key in (
            "source_manifest",
            "required_questions",
            "required_checks",
            "blind_spots",
            "gaps",
        ):
            value[key] = list(value[key])
        return value


_MALIK_SOURCES = (
    MethodSource(
        id="obs-portfolio-thread-2021-selection",
        label="OBS · portfel IKE i kryterium perspektyw",
        repo_path="docs/source-materials/obs.txt",
        sha256="7445d7c59f6e0a020c61fc3a0d2bc48fc890ae76043ee18a5d9c732560e99771",
        author_identity="Paweł Malik (OBS)",
        source_url="https://portalanaliz.pl/forum/viewtopic.php?f=7&t=569",
        locator="OBS — 2021-02-02T14:56:44+00:00",
        publication_at="2021-02-02T14:56:44+00:00",
        known_at=None,
        date_note=None,
        retention_status="retained",
    ),
    MethodSource(
        id="obs-portfolio-thread-2024-improvement",
        label="OBS · poprawa wyników, katalizator i ryzyko płynności",
        repo_path="docs/source-materials/obs.txt",
        sha256="7445d7c59f6e0a020c61fc3a0d2bc48fc890ae76043ee18a5d9c732560e99771",
        author_identity="Paweł Malik (OBS)",
        source_url="https://portalanaliz.pl/forum/viewtopic.php?f=7&t=569",
        locator="OBS — 2024-08-15T15:37:00+00:00",
        publication_at="2024-08-15T15:37:00+00:00",
        known_at=None,
        date_note=None,
        retention_status="retained",
    ),
    MethodSource(
        id="malik-biznesradar-excel-transcript",
        label="Transkrypcja: BiznesRadar → Excel → prognoza kwartału",
        repo_path="docs/source-materials/transkrypcja_biznesradar_excel.docx",
        sha256="df1ea20f2f4f804e8e7fb04fd08a3bb2da0a6d4183420768dddb4c8e38a4527a",
        author_identity="Paweł Malik (mówca); transkrybent niepodany",
        source_url=None,
        locator="00:00–11:07; część „Budowanie szybkiej prognozy na kolejny kwartał”",
        publication_at=None,
        known_at=None,
        date_note="Oryginalna data publikacji nie została zachowana; metadane lokalnego DOCX nie są datą źródła.",
        retention_status="retained",
    ),
)


_ELENDIX_SOURCES = (
    MethodSource(
        id="elendix-portfolio-thread-2022-discount-rate",
        label="Elendix · stopa dyskontowa a wartość przyszłych zysków",
        repo_path="docs/source-materials/obs.txt",
        sha256="7445d7c59f6e0a020c61fc3a0d2bc48fc890ae76043ee18a5d9c732560e99771",
        author_identity="Elendix (pseudonym)",
        source_url="https://portalanaliz.pl/forum/viewtopic.php?f=7&t=569",
        locator="Elendix — 2022-04-05T15:13:37+00:00",
        publication_at="2022-04-05T15:13:37+00:00",
        known_at=None,
        date_note=None,
        retention_status="retained",
    ),
    MethodSource(
        id="elendix-portfolio-thread-2024-risk-reward",
        label="Elendix · pytanie o risk/reward, płynność i pełny cykl inwestycji",
        repo_path="docs/source-materials/obs.txt",
        sha256="7445d7c59f6e0a020c61fc3a0d2bc48fc890ae76043ee18a5d9c732560e99771",
        author_identity="Elendix (pseudonym)",
        source_url="https://portalanaliz.pl/forum/viewtopic.php?f=7&t=569",
        locator="Elendix — 2024-08-15T18:20:54+00:00",
        publication_at="2024-08-15T18:20:54+00:00",
        known_at=None,
        date_note=None,
        retention_status="retained",
    ),
)


CATALOG = (
    ResearchMethodCatalogEntry(
        id="malik_obs_v1",
        version="malik-obs-method-v2",
        label="Paweł Malik / OBS",
        disclaimer=(
            "To wersjonowana perspektywa Workbench z materiałów źródłowych, nie bieżąca "
            "opinia, rekomendacja ani głos autora."
        ),
        stages={
            "discover": MethodStageReadiness(
                "planned",
                "Brak zachowanego, rynkowego snapshotu wszystkich wymaganych czynników.",
            ),
            "research": MethodStageReadiness(
                "supported",
                "Perspektywę można utworzyć wyłącznie jawną komendą dla zachowanego snapshotu Research.",
            ),
            "valuation": MethodStageReadiness("supported"),
        },
        evaluation_maturity="untested",
        skill="strategy-malik-obs",
        research_output_schema_version="research-method-perspective-v1",
        valuation_output_schema_version="valuation-snapshot-v1",
        calculation_engine_version="valuation-engine-v2",
        required_verifier_role="verifier_strict",
        source_manifest=_MALIK_SOURCES,
        required_questions=(
            "Jaki obserwowalny mechanizm może zmienić wynik w następnym kwartale lub roku?",
            "Czy przychody, marża brutto i koszty stałe tworzą spójny most wyniku?",
            "Która część wyniku jest trwała, a która jednorazowa lub zależna od warunków zewnętrznych?",
            "Jaki katalizator, horyzont i falsyfikator można sprawdzić w kolejnych źródłach?",
            "Czy gotówka, kapitał obrotowy, capex i zadłużenie zostawiają margines bezpieczeństwa?",
        ),
        required_checks=(
            MethodRequiredCheck(
                id="result-change-mechanism",
                label="Obserwowalny mechanizm zmiany wyniku w następnym kwartale lub roku.",
                origin="author-stated",
            ),
            MethodRequiredCheck(
                id="revenue-margin-cost-bridge",
                label="Spójność przychodów, marży brutto i kosztów stałych w moście wyniku.",
                origin="author-stated",
            ),
            MethodRequiredCheck(
                id="durable-versus-one-off",
                label="Rozdzielenie wyniku trwałego od jednorazowego lub zewnętrznego.",
                origin="author-stated",
            ),
            MethodRequiredCheck(
                id="catalyst-horizon-falsifier",
                label="Możliwy do sprawdzenia katalizator, horyzont i falsyfikator.",
                origin="author-stated",
            ),
            MethodRequiredCheck(
                id="cash-working-capital-capex-debt",
                label="Margines bezpieczeństwa z gotówki, kapitału obrotowego, capexu i zadłużenia.",
                origin="author-stated",
            ),
        ),
        blind_spots=(
            "Nie zastępuje źródłowego backlogu, cen, marż projektowych ani oceny zarządu.",
            "Nie daje uniwersalnego rankingu ani wyniku inwestycyjnego.",
            "Własna historia mnożnika jest tylko wrażliwością, dopóki brak porównywalnego szeregu point-in-time.",
        ),
        gaps=(
            "Perspektywa wymaga osobnej jawnej komendy i nie powstaje przy odczycie katalogu.",
            "Ocena „czy rynek już wycenił zmianę” pozostaje pytaniem Research, nie faktem z katalogu.",
        ),
    ),
    ResearchMethodCatalogEntry(
        id="areczeks_v1",
        version="areczeks-method-draft-v1",
        label="Areczeks",
        disclaimer="Metoda pozostaje szkicem; Workbench nie symuluje głosu ani wniosków autora.",
        stages={
            "discover": MethodStageReadiness("draft", "Brak zachowanych, datowanych materiałów źródłowych i danych rynkowych."),
            "research": MethodStageReadiness("draft", "Brak zachowanych, datowanych materiałów źródłowych."),
            "valuation": MethodStageReadiness("draft", "Brak zweryfikowanych reguł wyceny i kompatybilnego szablonu."),
        },
        evaluation_maturity="untested",
        skill=None,
        research_output_schema_version=None,
        valuation_output_schema_version=None,
        calculation_engine_version=None,
        required_verifier_role=None,
        source_manifest=(),
        required_questions=(),
        required_checks=(),
        blind_spots=(),
        gaps=("Nie aktywować bez zachowanych źródeł z dokładną atrybucją.",),
    ),
    ResearchMethodCatalogEntry(
        id="elendix_v1",
        version="elendix-method-draft-v2",
        label="Elendix",
        disclaimer="Metoda pozostaje szkicem; Workbench nie symuluje głosu ani wniosków autora.",
        stages={
            "discover": MethodStageReadiness("draft", "Częściowy korpus nie określa reguł selekcji ani rynkowych danych wejściowych."),
            "research": MethodStageReadiness("draft", "Dwa datowane fragmenty nie ustanawiają pełnej, odtwarzalnej metody Research."),
            "valuation": MethodStageReadiness("draft", "Jeden opis mechaniki stopy dyskontowej nie jest zweryfikowaną regułą wyceny ani szablonem."),
        },
        evaluation_maturity="untested",
        skill=None,
        research_output_schema_version=None,
        valuation_output_schema_version=None,
        calculation_engine_version=None,
        required_verifier_role=None,
        source_manifest=_ELENDIX_SOURCES,
        required_questions=(),
        required_checks=(),
        blind_spots=(),
        gaps=(
            "Zachowano dwa datowane fragmenty: jeden wyjaśnia mechanikę stopy dyskontowej, drugi jest pytaniem o risk/reward i proces inwestycji.",
            "Nie wyprowadzać z tych fragmentów reguł selekcji, wniosków spółkowych ani perspektywy autora.",
            "Przed aktywacją potrzebny jest pełniejszy, datowany materiał pierwotny z regułami oraz niezależny strict review.",
        ),
    ),
)


def list_research_method_catalog() -> list[dict]:
    return [entry.to_dict() for entry in CATALOG]


def get_research_method_catalog_entry(method_pack_id: str) -> ResearchMethodCatalogEntry | None:
    return next((entry for entry in CATALOG if entry.id == method_pack_id), None)


def canonical_manifest_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def freeze_research_method_manifest(method_pack_id: str) -> tuple[dict, str] | None:
    """Return the exact versioned method contract a perspective job may use."""
    entry = get_research_method_catalog_entry(method_pack_id)
    if entry is None:
        return None
    catalog = entry.to_dict()
    manifest = {
        "id": catalog["id"],
        "version": catalog["version"],
        "label": catalog["label"],
        "disclaimer": catalog["disclaimer"],
        "research_stage": catalog["stages"]["research"],
        "skill": catalog["skill"],
        "research_output_schema_version": catalog["research_output_schema_version"],
        "required_verifier_role": catalog["required_verifier_role"],
        "source_manifest": catalog["source_manifest"],
        "required_checks": catalog["required_checks"],
        "blind_spots": catalog["blind_spots"],
        "gaps": catalog["gaps"],
    }
    return manifest, canonical_manifest_fingerprint(manifest)
