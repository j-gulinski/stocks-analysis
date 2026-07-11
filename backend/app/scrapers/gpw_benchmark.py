"""Parser for GPW Benchmark's dated index-portfolio table."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class IndexPortfolio:
    as_of: date
    instruments: frozenset[str]


def parse_index_portfolio(html: str) -> IndexPortfolio:
    soup = BeautifulSoup(html, "html.parser")
    match = re.search(r"\b(\d{2})-(\d{2})-(\d{4})\b", soup.get_text(" ", strip=True))
    if not match:
        raise ParseError("Missing portfolio as-of date.")
    rows = soup.select("table tr")
    instruments = {
        cell.get_text(" ", strip=True).upper()
        for row in rows
        for cell in row.select("td:first-child")
        if re.fullmatch(r"[A-Z0-9._-]{2,12}", cell.get_text(" ", strip=True).upper())
    }
    if not instruments:
        raise ParseError("No portfolio instruments found.")
    return IndexPortfolio(date(int(match.group(3)), int(match.group(2)), int(match.group(1))), frozenset(instruments))
