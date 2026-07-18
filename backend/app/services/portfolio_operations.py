"""Preview-first import and read model for myfund operation-history CSV exports."""

from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import PortfolioOperation
from app.services.valuation_engine import canonical_hash


OPERATIONS_CSV_VERSION = "myfund-operations-csv-v1"
MAX_OPERATION_ROWS = 50_000

_HEADER_ALIASES = {
    "data": "date",
    "operacja": "operation",
    "typ operacji": "operation",
    "konto": "account",
    "walor": "instrument",
    "instrument": "instrument",
    "waluta": "currency",
    "liczba jednostek": "quantity",
    "liczba jednostek akcji": "quantity",
    "cena": "price",
    "prowizja": "commission",
    "podatek": "tax",
    "wartosc": "amount",
    "stan konta po operacji": "cash_balance_after",
    "stan konta": "cash_balance_after",
}
_REQUIRED_COLUMNS = {
    "date",
    "operation",
    "account",
    "instrument",
    "currency",
    "quantity",
    "price",
    "commission",
    "tax",
    "amount",
    "cash_balance_after",
}
_KIND_ALIASES = {
    "kupno": "buy",
    "sprzedaz": "sell",
    "wplata": "deposit",
    "wyplata": "withdrawal",
    "dywidenda": "dividend",
    "odsetki": "interest",
    "podatek": "tax",
    "zwrot podatku": "tax-refund",
    "prowizja": "fee",
}
_KIND_LABELS = {
    "buy": "Kupno",
    "sell": "Sprzedaż",
    "deposit": "Wpłata",
    "withdrawal": "Wypłata",
    "dividend": "Dywidenda",
    "interest": "Odsetki",
    "tax": "Podatek",
    "tax-refund": "Zwrot podatku",
    "fee": "Prowizja",
    "other": "Inna operacja",
}
_EXTERNAL_FLOW_KINDS = {"deposit", "withdrawal"}
_TERMINAL_TICKER = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,19})\)\s*$")


class PortfolioOperationsCsvError(ValueError):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(" ".join(issues))


@dataclass(frozen=True)
class ParsedPortfolioOperations:
    fingerprint: str
    rows: list[dict[str, Any]]
    summary: dict[str, Any]


def _normalized_text(value: Any) -> str:
    text = str(value or "").translate(str.maketrans({"ł": "l", "Ł": "L"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().casefold().split())


def _delimiter(content: str) -> str:
    header = next((line for line in content.splitlines() if line.strip()), "")
    candidates = {";": header.count(";"), "\t": header.count("\t"), ",": header.count(",")}
    delimiter, count = max(candidates.items(), key=lambda item: item[1])
    if count == 0:
        raise PortfolioOperationsCsvError(
            ["Plik nie ma rozpoznawalnego separatora CSV (;, tabulator lub przecinek)."]
        )
    return delimiter


def _number(value: Any, *, line: int, field: str) -> float | None:
    text = str(value or "").strip().replace("\u00a0", "").replace(" ", "")
    if text in {"", "-", "—"}:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        result = float(text)
    except ValueError as exc:
        raise PortfolioOperationsCsvError(
            [f"Wiersz {line}: pole „{field}” nie jest liczbą."]
        ) from exc
    if not math.isfinite(result):
        raise PortfolioOperationsCsvError(
            [f"Wiersz {line}: pole „{field}” nie jest skończoną liczbą."]
        )
    return result


def _occurred(value: Any, *, line: int) -> tuple[date, str | None]:
    text = str(value or "").strip()
    datetime_patterns = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
    )
    for pattern in datetime_patterns:
        try:
            occurred_at = datetime.strptime(text, pattern)
            return occurred_at.date(), occurred_at.isoformat(timespec="seconds")
        except ValueError:
            continue
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date(), None
        except ValueError:
            continue
    raise PortfolioOperationsCsvError(
        [
            f"Wiersz {line}: data musi mieć format RRRR-MM-DD, DD.MM.RRRR lub DD-MM-RRRR, "
            "opcjonalnie z czasem GG:MM[:SS]."
        ]
    )


def _row_value(row: dict[str, Any], columns: dict[str, str], key: str) -> Any:
    return row.get(columns[key])


def _row_hash_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row["raw"]
    return {
        "version": OPERATIONS_CSV_VERSION,
        "occurred_on": row["occurred_on"].isoformat(),
        "occurred_at": raw["occurred_at"],
        "source_order": raw["source_order"],
        "kind": row["kind"],
        "operation_label": raw["operation_label"],
        "account": raw["account"],
        "instrument_name": row["instrument_name"],
        "ticker": row["ticker"],
        "quantity": row["quantity"],
        "price": row["price"],
        "commission": raw["commission"],
        "tax": raw["tax"],
        "amount_pln": row["amount_pln"],
        "currency": row["currency"],
        "cash_balance_after": raw["cash_balance_after"],
    }


def _summary(rows: list[dict[str, Any]], *, defaulted_currency_rows: int) -> dict[str, Any]:
    dates = [row["occurred_on"] for row in rows]
    deposits = sum(
        float(row["amount_pln"] or 0) for row in rows if row["kind"] == "deposit"
    )
    withdrawals = sum(
        abs(float(row["amount_pln"] or 0))
        for row in rows
        if row["kind"] == "withdrawal"
    )
    return {
        "row_count": len(rows),
        "date_from": min(dates).isoformat() if dates else None,
        "date_to": max(dates).isoformat() if dates else None,
        "deposit_total_pln": round(deposits, 2),
        "withdrawal_total_pln": round(withdrawals, 2),
        "external_flow_count": sum(
            row["kind"] in _EXTERNAL_FLOW_KINDS for row in rows
        ),
        "unclassified_count": sum(row["kind"] == "other" for row in rows),
        "currency_defaulted_rows": defaulted_currency_rows,
    }


def parse_myfund_operations_csv(
    content: str, *, base_currency: str = "PLN"
) -> ParsedPortfolioOperations:
    """Parse the official operation-history table export without writing state."""
    normalized_base_currency = base_currency.strip().upper() or "PLN"
    if normalized_base_currency != "PLN":
        raise PortfolioOperationsCsvError(
            ["Import operacji wymaga portfela prowadzonego w PLN."]
        )
    if not content.strip():
        raise PortfolioOperationsCsvError(["Plik CSV jest pusty."])
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), delimiter=_delimiter(content))
    if not reader.fieldnames:
        raise PortfolioOperationsCsvError(["Plik CSV nie ma wiersza nagłówków."])
    columns: dict[str, str] = {}
    duplicate_columns: list[str] = []
    for original in reader.fieldnames:
        canonical = _HEADER_ALIASES.get(_normalized_text(original))
        if canonical is None:
            continue
        if canonical in columns:
            duplicate_columns.append(str(original))
        columns[canonical] = original
    missing = sorted(_REQUIRED_COLUMNS - set(columns))
    if duplicate_columns or missing:
        issues = []
        if missing:
            issues.append(
                "Brak kolumn z eksportu myfund: " + ", ".join(missing) + "."
            )
        if duplicate_columns:
            issues.append(
                "Powtórzone kolumny po normalizacji: "
                + ", ".join(duplicate_columns)
                + "."
            )
        raise PortfolioOperationsCsvError(issues)

    parsed: list[dict[str, Any]] = []
    issues: list[str] = []
    defaulted_currency_rows = 0
    for line, source in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in source.values()):
            continue
        date_text = str(_row_value(source, columns, "date") or "").strip()
        if _normalized_text(date_text) in {"bilans", "razem", "suma"}:
            continue
        try:
            occurred_on, occurred_at = _occurred(date_text, line=line)
            if occurred_on > date.today():
                raise PortfolioOperationsCsvError(
                    [f"Wiersz {line}: operacja nie może mieć daty przyszłej."]
                )
            operation_label = str(
                _row_value(source, columns, "operation") or ""
            ).strip()
            instrument_name = str(
                _row_value(source, columns, "instrument") or ""
            ).strip()
            if not operation_label or not instrument_name:
                raise PortfolioOperationsCsvError(
                    [f"Wiersz {line}: operacja i walor są wymagane."]
                )
            kind = _KIND_ALIASES.get(_normalized_text(operation_label), "other")
            currency = str(_row_value(source, columns, "currency") or "").strip().upper()
            if not currency:
                currency = normalized_base_currency
                defaulted_currency_rows += 1
            if not re.fullmatch(r"[A-Z]{3,10}", currency):
                raise PortfolioOperationsCsvError(
                    [f"Wiersz {line}: waluta ma nieprawidłowy format."]
                )
            if currency != normalized_base_currency:
                raise PortfolioOperationsCsvError(
                    [
                        f"Wiersz {line}: eksport musi pokazywać Wartość w walucie portfela "
                        f"({normalized_base_currency})."
                    ]
                )
            quantity = _number(
                _row_value(source, columns, "quantity"), line=line, field="Liczba jednostek"
            )
            price = _number(_row_value(source, columns, "price"), line=line, field="Cena")
            commission = _number(
                _row_value(source, columns, "commission"), line=line, field="Prowizja"
            )
            tax = _number(_row_value(source, columns, "tax"), line=line, field="Podatek")
            amount = _number(
                _row_value(source, columns, "amount"), line=line, field="Wartość"
            )
            cash_balance_after = _number(
                _row_value(source, columns, "cash_balance_after"),
                line=line,
                field="Stan konta po operacji",
            )
            if amount is None:
                raise PortfolioOperationsCsvError(
                    [f"Wiersz {line}: Wartość operacji jest wymagana."]
                )
            if price is not None and price < 0:
                raise PortfolioOperationsCsvError([f"Wiersz {line}: Cena nie może być ujemna."])
            if commission is not None and commission < 0:
                raise PortfolioOperationsCsvError(
                    [f"Wiersz {line}: Prowizja nie może być ujemna."]
                )
            if tax is not None and tax < 0:
                raise PortfolioOperationsCsvError([f"Wiersz {line}: Podatek nie może być ujemny."])
            expected_amount_sign = {
                "buy": -1,
                "sell": 1,
                "deposit": 1,
                "withdrawal": -1,
            }.get(kind)
            if expected_amount_sign and amount * expected_amount_sign <= 0:
                raise PortfolioOperationsCsvError(
                    [f"Wiersz {line}: znak Wartości nie zgadza się z typem operacji."]
                )
            if kind == "buy" and (quantity is None or quantity <= 0):
                raise PortfolioOperationsCsvError(
                    [f"Wiersz {line}: kupno wymaga dodatniej Liczby jednostek."]
                )
            if kind == "sell" and (quantity is None or quantity >= 0):
                raise PortfolioOperationsCsvError(
                    [f"Wiersz {line}: sprzedaż wymaga ujemnej Liczby jednostek."]
                )
            if kind in {"buy", "sell"} and quantity is not None and price is not None:
                # myfund exposes tax separately; Wartość is the cash value of
                # the transaction itself and includes commission, not tax.
                fees = float(commission or 0)
                gross = abs(quantity) * price
                expected_amount = -(gross + fees) if kind == "buy" else gross - fees
                tolerance = max(0.02, abs(expected_amount) * 0.000001)
                if abs(amount - expected_amount) > tolerance:
                    raise PortfolioOperationsCsvError(
                        [
                            f"Wiersz {line}: Wartość nie uzgadnia się z liczbą jednostek, "
                            "ceną i prowizją (podatek jest w eksporcie osobną wartością)."
                        ]
                    )
            ticker_match = _TERMINAL_TICKER.search(instrument_name.upper())
            parsed.append(
                {
                    "occurred_on": occurred_on,
                    "kind": kind,
                    "instrument_name": instrument_name,
                    "ticker": ticker_match.group(1) if ticker_match else None,
                    "quantity": quantity,
                    "price": price,
                    "amount_pln": amount,
                    "currency": currency,
                    "provider_key": None,
                    "raw": {
                        "source_version": OPERATIONS_CSV_VERSION,
                        "occurred_at": occurred_at,
                        "source_order": line - 2,
                        "operation_label": operation_label,
                        "account": str(
                            _row_value(source, columns, "account") or ""
                        ).strip(),
                        "commission": commission,
                        "tax": tax,
                        "cash_balance_after": cash_balance_after,
                        "currency_defaulted": not bool(
                            str(_row_value(source, columns, "currency") or "").strip()
                        ),
                    },
                }
            )
        except PortfolioOperationsCsvError as exc:
            issues.extend(exc.issues)
            if len(issues) >= 20:
                break
        if len(parsed) > MAX_OPERATION_ROWS:
            issues.append(f"Plik przekracza limit {MAX_OPERATION_ROWS} operacji.")
            break
    if issues:
        raise PortfolioOperationsCsvError(issues)
    if not parsed:
        raise PortfolioOperationsCsvError(["Plik nie zawiera żadnej operacji."])

    base_hashes = [canonical_hash(_row_hash_payload(row)) for row in parsed]
    occurrences: Counter[str] = Counter()
    for row, base_hash in zip(parsed, base_hashes, strict=True):
        occurrences[base_hash] += 1
        row["content_hash"] = canonical_hash(
            {
                "version": OPERATIONS_CSV_VERSION,
                "base_hash": base_hash,
                "occurrence": occurrences[base_hash],
            }
        )
    fingerprint = canonical_hash(
        {
            "version": OPERATIONS_CSV_VERSION,
            "operations": [row["content_hash"] for row in parsed],
        }
    )
    return ParsedPortfolioOperations(
        fingerprint=fingerprint,
        rows=parsed,
        summary=_summary(parsed, defaulted_currency_rows=defaulted_currency_rows),
    )


def _operation_out(row: PortfolioOperation) -> dict[str, Any]:
    raw = row.raw or {}
    return {
        "id": row.id,
        "occurred_on": row.occurred_on.isoformat(),
        "occurred_at": raw.get("occurred_at"),
        "kind": row.kind,
        "kind_label": raw.get("operation_label") or _KIND_LABELS.get(row.kind, row.kind),
        "instrument_name": row.instrument_name,
        "ticker": row.ticker,
        "quantity": row.quantity,
        "price": row.price,
        "commission": raw.get("commission"),
        "tax": raw.get("tax"),
        "amount_pln": row.amount_pln,
        "currency": row.currency,
        "cash_balance_after": raw.get("cash_balance_after"),
        "source": row.source,
    }


def operations_preview(parsed: ParsedPortfolioOperations) -> dict[str, Any]:
    return {
        "version": OPERATIONS_CSV_VERSION,
        "fingerprint": parsed.fingerprint,
        "summary": parsed.summary,
        "sample": [
            {
                **{key: value for key, value in row.items() if key not in {"raw", "content_hash"}},
                "occurred_on": row["occurred_on"].isoformat(),
                "occurred_at": row["raw"]["occurred_at"],
                "kind_label": row["raw"]["operation_label"],
                "commission": row["raw"]["commission"],
                "tax": row["raw"]["tax"],
                "cash_balance_after": row["raw"]["cash_balance_after"],
            }
            for row in parsed.rows[:10]
        ],
    }


def replace_csv_operations(
    db: Session, *, portfolio_id: int, parsed: ParsedPortfolioOperations
) -> dict[str, Any]:
    existing = list(
        db.scalars(
            select(PortfolioOperation).where(
                PortfolioOperation.portfolio_id == portfolio_id,
                PortfolioOperation.source == "csv",
            )
        )
    )
    existing_hashes = sorted(row.content_hash for row in existing)
    parsed_hashes = sorted(row["content_hash"] for row in parsed.rows)
    if existing_hashes == parsed_hashes:
        return {
            "changed": False,
            "replaced_count": 0,
            "imported_count": len(existing),
            "fingerprint": parsed.fingerprint,
        }
    db.execute(
        delete(PortfolioOperation).where(
            PortfolioOperation.portfolio_id == portfolio_id,
            PortfolioOperation.source == "csv",
        )
    )
    for row in parsed.rows:
        db.add(
            PortfolioOperation(
                portfolio_id=portfolio_id,
                occurred_on=row["occurred_on"],
                kind=row["kind"],
                instrument_name=row["instrument_name"],
                ticker=row["ticker"],
                quantity=row["quantity"],
                price=row["price"],
                amount_pln=row["amount_pln"],
                currency=row["currency"],
                source="csv",
                provider_key=row["provider_key"],
                content_hash=row["content_hash"],
                raw=row["raw"],
            )
        )
    db.commit()
    return {
        "changed": True,
        "replaced_count": len(existing),
        "imported_count": len(parsed.rows),
        "fingerprint": parsed.fingerprint,
    }


def portfolio_operations_workspace(
    db: Session, *, portfolio_id: int, history: list[dict[str, Any]]
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(PortfolioOperation)
            .where(PortfolioOperation.portfolio_id == portfolio_id)
            .order_by(PortfolioOperation.occurred_on.desc(), PortfolioOperation.id.desc())
        )
    )
    if not rows:
        return {
            "status": "missing",
            "version": OPERATIONS_CSV_VERSION,
            "count": 0,
            "date_from": None,
            "date_to": None,
            "deposit_total_pln": 0.0,
            "withdrawal_total_pln": 0.0,
            "unclassified_count": 0,
            "currency_defaulted_rows": 0,
            "content_fingerprint": None,
            "flow_reconciliation": {
                "status": "unavailable",
                "matched_days": 0,
                "mismatches": [],
                "provider_contribution_change_pln": None,
                "operation_external_flow_pln": None,
            },
            "recent": [],
            "gaps": [
                "Brak historii operacji; TWR/XIRR opiera się wyłącznie na dziennej serii wartości i wkładu myfund."
            ],
        }

    def recent_key(row: PortfolioOperation) -> tuple[date, time, int]:
        raw = row.raw or {}
        occurred_at = raw.get("occurred_at")
        occurred_time = (
            datetime.fromisoformat(str(occurred_at)).time()
            if occurred_at
            else time.min
        )
        tie_order = (
            -int(raw["source_order"])
            if raw.get("source_order") is not None
            else row.id
        )
        return row.occurred_on, occurred_time, tie_order

    public_rows = [_operation_out(row) for row in sorted(rows, key=recent_key, reverse=True)]
    dates = [row.occurred_on for row in rows]
    csv_rows = sorted(
        (row for row in rows if row.source == "csv"),
        key=lambda row: int((row.raw or {}).get("source_order", row.id)),
    )
    csv_hashes = [row.content_hash for row in csv_rows]
    defaulted = sum(bool((row.raw or {}).get("currency_defaulted")) for row in rows)
    unclassified = sum(row.kind == "other" for row in rows)
    deposits = sum(float(row.amount_pln or 0) for row in rows if row.kind == "deposit")
    withdrawals = sum(
        abs(float(row.amount_pln or 0)) for row in rows if row.kind == "withdrawal"
    )

    operation_flows: dict[date, float] = defaultdict(float)
    for row in rows:
        if row.kind in _EXTERNAL_FLOW_KINDS and row.amount_pln is not None:
            operation_flows[row.occurred_on] += float(row.amount_pln)
    sorted_history = sorted(history, key=lambda row: str(row.get("date")))
    contribution_changes: dict[date, float] = {}
    for previous, current in zip(sorted_history, sorted_history[1:]):
        if previous.get("contributed") is None or current.get("contributed") is None:
            continue
        current_date = date.fromisoformat(str(current["date"]))
        contribution_changes[current_date] = float(current["contributed"]) - float(
            previous["contributed"]
        )
    history_start = (
        date.fromisoformat(str(sorted_history[0]["date"])) if sorted_history else None
    )
    history_end = (
        date.fromisoformat(str(sorted_history[-1]["date"])) if sorted_history else None
    )
    covers_history_start = bool(history_start and min(dates) <= history_start)
    comparison_start = history_start if covers_history_start else min(dates)
    comparison_dates = sorted(
        day
        for day in set(contribution_changes) | set(operation_flows)
        if comparison_start is not None
        and (
            day > comparison_start if covers_history_start else day >= comparison_start
        )
        and (history_end is None or day <= history_end)
        and (
            abs(contribution_changes.get(day, 0.0)) > 0.005
            or abs(operation_flows.get(day, 0.0)) > 0.005
        )
    )
    mismatches = [
        {
            "date": day.isoformat(),
            "provider_contribution_change_pln": round(
                contribution_changes.get(day, 0.0), 2
            ),
            "operation_external_flow_pln": round(operation_flows.get(day, 0.0), 2),
        }
        for day in comparison_dates
        if abs(contribution_changes.get(day, 0.0) - operation_flows.get(day, 0.0))
        > 0.02
    ]
    if not sorted_history:
        flow_status = "unavailable"
    elif mismatches:
        flow_status = "mismatch"
    elif not covers_history_start:
        flow_status = "partial"
    else:
        flow_status = "reconciled"
    gaps: list[str] = []
    if not covers_history_start and history_start:
        gaps.append(
            "Import operacji zaczyna się po początku dziennej historii myfund; uzgodnienie przepływów jest częściowe."
        )
    if mismatches:
        gaps.append(
            f"Historia operacji nie uzgadnia {len(mismatches)} dni zmian wkładu myfund."
        )
    if unclassified:
        gaps.append(
            f"{unclassified} typów operacji pozostaje widocznych jako inne i nie wchodzi do uzgodnienia przepływów zewnętrznych."
        )
    if defaulted:
        gaps.append(
            f"Dla {defaulted} operacji bez waluty użyto waluty bazowej portfela."
        )
    return {
        "status": "imported",
        "version": OPERATIONS_CSV_VERSION,
        "count": len(rows),
        "date_from": min(dates).isoformat(),
        "date_to": max(dates).isoformat(),
        "deposit_total_pln": round(deposits, 2),
        "withdrawal_total_pln": round(withdrawals, 2),
        "unclassified_count": unclassified,
        "currency_defaulted_rows": defaulted,
        "content_fingerprint": (
            canonical_hash(
                {"version": OPERATIONS_CSV_VERSION, "operations": csv_hashes}
            )
            if csv_hashes
            else None
        ),
        "flow_reconciliation": {
            "status": flow_status,
            "matched_days": len(comparison_dates) - len(mismatches),
            "mismatches": mismatches[:20],
            "provider_contribution_change_pln": (
                round(sum(contribution_changes.get(day, 0.0) for day in comparison_dates), 2)
                if comparison_dates
                else 0.0
            ),
            "operation_external_flow_pln": (
                round(sum(operation_flows.get(day, 0.0) for day in comparison_dates), 2)
                if comparison_dates
                else 0.0
            ),
        },
        "recent": public_rows[:20],
        "gaps": gaps,
    }


def portfolio_operation_cost_basis(
    db: Session, *, portfolio_id: int
) -> dict[str, dict[str, Any]]:
    """Rebuild remaining average cost only for exact, classified ticker ledgers."""
    rows = list(
        db.scalars(
            select(PortfolioOperation)
            .where(
                PortfolioOperation.portfolio_id == portfolio_id,
                PortfolioOperation.ticker.is_not(None),
            )
        )
    )

    def replay_key(row: PortfolioOperation) -> tuple[date, time, int]:
        raw = row.raw or {}
        occurred_at = raw.get("occurred_at")
        occurred_time = (
            datetime.fromisoformat(str(occurred_at)).time()
            if occurred_at
            else time.min
        )
        return (
            row.occurred_on,
            occurred_time,
            int(raw.get("source_order", row.id)),
        )

    rows.sort(key=replay_key)
    same_day_kinds: dict[tuple[str, date], set[str]] = defaultdict(set)
    date_only_days: set[tuple[str, date]] = set()
    same_timestamp_kinds: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row.ticker and row.kind in {"buy", "sell"}:
            ticker = row.ticker.upper()
            day_key = (ticker, row.occurred_on)
            same_day_kinds[day_key].add(row.kind)
            occurred_at = (row.raw or {}).get("occurred_at")
            if occurred_at:
                same_timestamp_kinds[(ticker, str(occurred_at))].add(row.kind)
            else:
                date_only_days.add(day_key)
    ambiguous_tickers = {
        ticker
        for (ticker, day), kinds in same_day_kinds.items()
        if kinds == {"buy", "sell"} and (ticker, day) in date_only_days
    } | {
        ticker
        for (ticker, _), kinds in same_timestamp_kinds.items()
        if kinds == {"buy", "sell"}
    }
    ledgers: dict[str, dict[str, Any]] = {}
    for row in rows:
        assert row.ticker is not None
        ticker = row.ticker.upper()
        ledger = ledgers.setdefault(
            ticker,
            {"quantity": 0.0, "cost_basis": 0.0, "status": "reconciled", "gaps": []},
        )
        if ticker in ambiguous_tickers:
            ledger["status"] = "unavailable"
            ledger["gaps"].append(
                "Kupno i sprzedaż nie mają czasu pozwalającego ustalić pewną kolejność; koszt z operacji jest niepublikowany."
            )
        if row.kind not in {"buy", "sell"}:
            if row.quantity not in {None, 0}:
                ledger["status"] = "unavailable"
                ledger["gaps"].append(
                    f"Operacja „{(row.raw or {}).get('operation_label') or row.kind}” zmienia liczbę jednostek poza obsługiwanym kupnem/sprzedażą."
                )
            continue
        if row.quantity is None or row.amount_pln is None:
            ledger["status"] = "unavailable"
            ledger["gaps"].append("Kupno lub sprzedaż nie ma liczby jednostek albo wartości.")
            continue
        quantity = float(row.quantity)
        if row.kind == "buy":
            ledger["quantity"] += quantity
            ledger["cost_basis"] += abs(float(row.amount_pln))
            continue
        sold = abs(quantity)
        if ledger["quantity"] <= 0 or sold - ledger["quantity"] > 0.000001:
            ledger["status"] = "unavailable"
            ledger["gaps"].append("Sprzedaż przekracza liczbę jednostek odtworzoną z importu.")
            continue
        average_cost = ledger["cost_basis"] / ledger["quantity"]
        ledger["quantity"] -= sold
        ledger["cost_basis"] -= average_cost * sold
    for ledger in ledgers.values():
        ledger["quantity"] = round(float(ledger["quantity"]), 8)
        ledger["cost_basis"] = round(max(0.0, float(ledger["cost_basis"])), 2)
        ledger["gaps"] = list(dict.fromkeys(ledger["gaps"]))
    return ledgers
