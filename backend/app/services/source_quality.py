"""Deterministic source-class notes used by evidence APIs and reviewers."""
from __future__ import annotations


SOURCE_QUALITY: dict[str, dict] = {
    "financial_report": {
        "priority": 0,
        "label": "Agregator danych finansowych",
        "allowed_use": "Bieżące wskaźniki, sprawozdania i kontekst do odkrywania.",
        "limitation": "Nie jest samodzielnym dowodem zdarzenia materialnego; porównaj z raportem emitenta.",
    },
    "market_indicators": {
        "priority": 0,
        "label": "Agregator wskaźników rynkowych",
        "allowed_use": "Bieżąca orientacja wycenowa i historyczne szeregi pomocnicze.",
        "limitation": "Definicje i korekty mogą różnić się od danych emitenta; nie używaj samodzielnie do tezy.",
    },
    "market_rating": {
        "priority": 0,
        "label": "Źródło odkrywania kandydatów",
        "allowed_use": "Wstępna selekcja i kolejność dalszego researchu.",
        "limitation": "Ocena zewnętrzna nie potwierdza jakości spółki ani potencjału inwestycyjnego.",
    },
    "issuer_ir": {
        "priority": 1,
        "label": "Oficjalny indeks relacji inwestorskich",
        "allowed_use": "Odnajdywanie raportów i komunikatów opublikowanych przez emitenta.",
        "limitation": "Sam tytuł/link jest niezweryfikowaną wskazówką; wniosek wymaga treści dokumentu.",
    },
    "issuer_ir_report": {
        "priority": 1,
        "label": "Dokument emitenta",
        "allowed_use": "Pierwotny dowód raportu, wyniku, governance lub komunikatu spółki.",
        "limitation": "Twierdzenia wymagają lokatora strony i kontroli statusu parsowania; ekstrakcja jest ograniczona do 30 stron i 4000 znaków na stronę, a skan może wymagać OCR.",
    },
    "espi_ebi": {
        "priority": 1,
        "label": "Oficjalny raport ESPI/EBI",
        "allowed_use": "Pierwotny dowód zdarzenia raportowanego przez emitenta.",
        "limitation": "Opis emitenta nie jest niezależną oceną skutku; interpretacja wymaga weryfikacji.",
    },
}

DEFAULT_SOURCE_QUALITY = {
    "priority": None,
    "label": "Źródło niesklasyfikowane",
    "allowed_use": "Tylko jako wskazówka do dalszej weryfikacji.",
    "limitation": "Brak zatwierdzonej noty jakości; nie używaj do twierdzeń decyzyjnych.",
}


def source_quality_note(source_type: str) -> dict:
    """Return a copy so API callers cannot mutate the registry."""
    note = SOURCE_QUALITY.get(source_type, DEFAULT_SOURCE_QUALITY)
    return {
        **note,
        "terms_status": "review_required",
        "terms_note": (
            "Dostęp wyłącznie przez uprzejmy, limitowany adapter; warunki ponownego "
            "wykorzystania nie są w aplikacji uznane za zweryfikowane."
        ),
        "rate_policy": "Wspólny klient HTTP: limity per domena, jitter, backoff i cache.",
    }
