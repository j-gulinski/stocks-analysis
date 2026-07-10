"""Structured PortalAnaliz storage.

Forum pages are parsed transiently, then reduced to activity metrics and
normalized claim summaries. Raw message bodies are not persisted by syncs.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, ForumIntelligence, ForumPost, ForumTopic
from app.scrapers import portalanaliz
from app.services import market_data

_FACT_KEYWORDS = (
    "akwizyc", "capex", "c/z", "cz", "cena docel", "certyfik", "cło",
    "rekomend", "dywidend", "ebitda", "eps", "espi", "uruchom",
    "przesuni", "opóź", "opozn", "kontrakt", "koszt", "marż", "zamów",
    "zamow", "backlog", "fabryk", "guidance", "insider", "kurs", "linia",
    "lockup", "popyt", "przychod", "prognoz", "ryzyk", "sprzedaż",
    "sprzedaz", "steam", "wishlist", "wynik", "zarząd", "zarzad",
    "q1", "q2", "q3", "q4",
)
_POSITIVE_WORDS = (
    "dobr", "lepsz", "popraw", "rośnie", "rosnie", "wzrost", "rekord",
    "uruchom", "kontrakt", "backlog",
)
_NEGATIVE_WORDS = (
    "słab", "slab", "spad", "opóź", "opozn", "przesuni", "ryzyk", "koszt",
    "strat", "problem",
)
_PERIOD_RE = re.compile(r"\b(q[1-4]\s*20\d{2}|20\d{2}\s*q[1-4]|20\d{2})\b", re.I)
_NUMBER_RE = re.compile(r"\b\d+(?:[,.]\d+)?\s*(?:mln|tys\.?|%|zł|pln|eur)?\b", re.I)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sentence_candidates(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [" ".join(p.split()) for p in parts if p and len(p.strip()) >= 12]


def _topic_for(sentence: str) -> str:
    lowered = sentence.lower()
    if "c/z" in lowered or "cena docel" in lowered or "kurs" in lowered:
        return "Wycena / sentyment"
    if "przychod" in lowered or "marż" in lowered or "ebitda" in lowered or "eps" in lowered or "wynik" in lowered:
        return "Oczekiwania finansowe"
    if "dywidend" in lowered or "rekomend" in lowered:
        return "Dywidenda"
    if "fabryk" in lowered or "linia" in lowered or "uruchom" in lowered:
        return "Moce produkcyjne"
    if "backlog" in lowered or "kontrakt" in lowered or "zamów" in lowered or "zamow" in lowered:
        return "Portfel zamówień"
    if "opóź" in lowered or "opozn" in lowered or "przesuni" in lowered:
        return "Opóźnienie / harmonogram"
    if "prognoz" in lowered:
        return "Prognoza"
    if "zarząd" in lowered or "zarzad" in lowered or "insider" in lowered:
        return "Zarząd / insiderzy"
    if "ryzyk" in lowered or "koszt" in lowered or "cło" in lowered:
        return "Ryzyka"
    return "Fakt do weryfikacji"


def _fact_type(sentence: str) -> str:
    lowered = sentence.lower()
    if any(word in lowered for word in ("opóź", "opozn", "ryzyk", "koszt", "problem", "spad")):
        return "risk"
    if any(word in lowered for word in ("uruchom", "kontrakt", "backlog", "certyfik", "steam", "wishlist")):
        return "catalyst"
    if any(word in lowered for word in ("prognoz", "oczek", "q1", "q2", "q3", "q4", "202")):
        return "expectation"
    if any(word in lowered for word in ("c/z", "cena docel", "kurs", "wycen")):
        return "valuation"
    if "dywidend" in lowered:
        return "dividend"
    return "fact_claim"


def _polarity(sentence: str) -> str:
    lowered = sentence.lower()
    positive = sum(1 for word in _POSITIVE_WORDS if word in lowered)
    negative = sum(1 for word in _NEGATIVE_WORDS if word in lowered)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def _confidence(sentence: str) -> str:
    lowered = sentence.lower()
    if "raport" in lowered or "zarząd" in lowered or "zarzad" in lowered or "rekomend" in lowered:
        return "confirmed"
    if _PERIOD_RE.search(lowered) or _NUMBER_RE.search(lowered):
        return "high"
    return "medium"


def _short_context(sentence: str) -> dict:
    periods = list(dict.fromkeys(p.group(0).upper().replace(" ", "") for p in _PERIOD_RE.finditer(sentence)))
    numbers = list(dict.fromkeys(n.group(0).replace(",", ".") for n in _NUMBER_RE.finditer(sentence)))[:4]
    metrics: list[str] = []
    lowered = sentence.lower()
    for key, label in (
        ("przychod", "przychody"),
        ("ebitda", "EBITDA"),
        ("eps", "EPS"),
        ("marż", "marża"),
        ("fcf", "FCF"),
        ("c/z", "C/Z"),
        ("dywidend", "dywidenda"),
        ("backlog", "backlog"),
    ):
        if key in lowered:
            metrics.append(label)
    return {"periods": periods[:3], "numbers": numbers, "metrics": list(dict.fromkeys(metrics))}


def _normalized_fact(sentence: str) -> str:
    """Return a non-verbatim claim summary with extracted anchors."""
    topic = _topic_for(sentence)
    context = _short_context(sentence)
    lowered = sentence.lower()
    if topic == "Dywidenda":
        base = "Forum wskazuje temat dywidendy lub rekomendacji zarządu"
    elif topic == "Moce produkcyjne":
        base = "Forum wskazuje temat uruchomienia lub zmiany mocy produkcyjnych"
    elif topic == "Portfel zamówień":
        base = "Forum wskazuje temat kontraktów, backlogu lub zamówień"
    elif topic == "Opóźnienie / harmonogram":
        base = "Forum wskazuje ryzyko przesunięcia harmonogramu"
    elif topic == "Oczekiwania finansowe":
        base = "Forum wskazuje oczekiwania finansowe do weryfikacji"
    elif topic == "Wycena / sentyment":
        base = "Forum wskazuje dyskusję o wycenie lub sentymencie"
    elif "steam" in lowered or "wishlist" in lowered:
        base = "Forum wskazuje hipotezę związaną ze Steam lub wishlistami"
    else:
        base = f"Forum wskazuje temat: {topic.lower()}"

    extras: list[str] = []
    if context["metrics"]:
        extras.append("metryki: " + ", ".join(context["metrics"]))
    if context["periods"]:
        extras.append("okresy: " + ", ".join(context["periods"]))
    if context["numbers"]:
        extras.append("liczby: " + ", ".join(context["numbers"]))
    return base + (f" ({'; '.join(extras)})" if extras else "")


def extract_distilled_facts(
    posts: list[portalanaliz.ParsedPost], *, limit: int = 20
) -> list[dict]:
    """Small local extraction pass over transient post text."""
    facts: list[dict] = []
    seen: set[str] = set()
    for post in posts:
        for sentence in _sentence_candidates(post.content_text):
            lowered = sentence.lower()
            if not any(keyword in lowered for keyword in _FACT_KEYWORDS):
                continue
            fact = _normalized_fact(sentence)
            key = " ".join(fact.lower().split())
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                {
                    "topic": _topic_for(sentence),
                    "type": _fact_type(sentence),
                    "polarity": _polarity(sentence),
                    "fact": fact,
                    "confidence": _confidence(sentence),
                    "source_post_ids": [post.phpbb_post_id],
                }
            )
            if len(facts) >= limit:
                return facts
    return facts


def _merge_facts(existing: list, new: list[dict], *, limit: int = 80) -> list[dict]:
    merged: dict[str, dict] = {}
    order: list[str] = []
    for item in list(existing or []) + list(new or []):
        if not isinstance(item, dict):
            continue
        fact = str(item.get("fact") or "").strip()
        if not fact:
            continue
        if not fact.startswith("Forum wskazuje"):
            fact = _normalized_fact(fact)
        key = " ".join(fact.lower().split())
        if key not in merged:
            merged[key] = {
                "topic": item.get("topic") or "Fakt do weryfikacji",
                "type": item.get("type") or "fact_claim",
                "polarity": item.get("polarity") or "neutral",
                "fact": fact[:280],
                "confidence": item.get("confidence") or "medium",
                "source_post_ids": list(item.get("source_post_ids") or []),
            }
            order.append(key)
        else:
            ids = merged[key]["source_post_ids"]
            for post_id in item.get("source_post_ids") or []:
                if post_id not in ids:
                    ids.append(post_id)
    return [merged[key] for key in order[-limit:]]


def _activity(posts: list[ForumPost]) -> tuple[int, int, list[dict]]:
    cutoff = _now_utc() - timedelta(days=30)
    recent = [
        p
        for p in posts
        if p.posted_at is not None
        and (p.posted_at if p.posted_at.tzinfo else p.posted_at.replace(tzinfo=timezone.utc)) >= cutoff
    ]
    users = {p.author for p in recent if p.author}
    by_day: Counter[str] = Counter()
    for post in recent:
        by_day[post.posted_at.date().isoformat()] += 1
    if not by_day:
        return 0, 0, []
    avg = sum(by_day.values()) / len(by_day)
    threshold = max(5, int(avg * 2))
    spikes = [
        {"date": day, "post_count": count}
        for day, count in sorted(by_day.items())
        if count >= threshold
    ]
    return len(recent), len(users), spikes


def _sentiment(facts: list[dict], post_count: int) -> str:
    positive = sum(1 for fact in facts if fact.get("polarity") == "positive")
    negative = sum(1 for fact in facts if fact.get("polarity") == "negative")
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "active" if post_count else "neutral"


def update_for_topic_pages(
    db: Session,
    topic: ForumTopic,
    pages: list[portalanaliz.TopicPage],
) -> ForumIntelligence | None:
    if topic.company_id is None:
        return None
    company = db.get(Company, topic.company_id)
    if company is None:
        return None

    record = db.scalar(
        select(ForumIntelligence).where(
            ForumIntelligence.company_id == company.id,
            ForumIntelligence.source == "portal_analiz",
        )
    )
    new_facts: list[dict] = []
    for page in pages:
        new_facts.extend(extract_distilled_facts(page.posts))

    posts = db.scalars(
        select(ForumPost)
        .join(ForumTopic, ForumPost.topic_id == ForumTopic.id)
        .where(ForumTopic.company_id == company.id)
    ).all()
    post_count, user_count, spikes = _activity(posts)
    facts = _merge_facts(record.distilled_facts if record else [], new_facts)
    industry_type = market_data.classify_industry_type(company.sector)

    payload = {
        "industry_type": industry_type,
        "last_30d_post_count": post_count,
        "last_30d_active_user_count": user_count,
        "activity_spikes": spikes,
        "community_sentiment": _sentiment(facts, post_count),
        "distilled_facts": facts,
    }
    if record is None:
        record = ForumIntelligence(
            company_id=company.id,
            source="portal_analiz",
            **payload,
        )
        db.add(record)
    else:
        for key, value in payload.items():
            setattr(record, key, value)
    return record
