# Walidacja silnika scenariuszy i wyceny potencjału — stage SC / WP5

Stage SC / WP5 (`docs/plan-stage-scenarios.md`). Cel: fixture-first walidacja
deterministycznego silnika scenariuszy (`services/scenarios.py`), refinera AI
(`services/scenarios_ai.py`) i agenta wyceny potencjału
(`services/valuation_ai.py`) + wzbogaconego korpusu `WorkedCase`
(`services/strategies/cases.py`) — mirror `docs/validation-thesis.md` (ten sam
styl i te same reguły uczciwości). Data: 2026-07-08.

## Metoda i realia środowiska (uczciwie, bez papierowania)

- **Ścieżka silnika: DETERMINISTYCZNA** w tym dokumencie. Każda liczba niżej
  pochodzi z REALNEGO uruchomienia `scenarios.build_scenario_set(...)` /
  `valuation_ai.assess_potential(...)` w TEJ sesji (nie z przepisanych
  komentarzy testów) — transkrypty poniżej.
- **Ścieżka AI** (`scenarios_ai.simulate_scenarios` / `valuation_ai.assess_potential`
  z kluczem) ćwiczona WYŁĄCZNIE przez `StubTransport` w `tests/test_scenarios_ai.py`
  (14/14) i `tests/test_valuation_ai.py` (25/25). Realne wywołanie API
  (`scripts/scenarios_smoke.py`) odłożone na maszynę użytkownika.
- **Ścieżka DB/API** (`dossier.py` wiring, `schemas.py`) — compile-checked
  (`py_compile`) w sesji; sandbox nie ma SQLAlchemy/Pydantic/FastAPI, więc
  `dossier.build_dossier` samo nie jest tu wykonywane.
- **Sandbox Python/proxy: BRAK egressu**, potwierdzone PONOWNIE w tej sesji
  (patrz „Walidacja live" niżej) — identycznie jak w stage TH.
- Scenariusze/wycena **nie dodają nowych źródeł scrapowania** (plan
  §Non-goals: „No new scraping sources") — konsumują pola już policzone przez
  wcześniejsze fazy (`multiple_history`, `eps`, `book_value`, `ebitda_ttm`,
  `net_cash`, `current_price`). „Fixture" na tym poziomie = ręcznie budowane
  `ScenarioInputs` (jak w `tests/test_scenarios.py`), analogicznie do
  archetypów small/mid/large w `tests/test_thesis.py`. Jeden z przykładów
  niżej dodatkowo REUŻYWA prawdziwych liczb z commitowanego fixture'a DEC
  (`br_indicators_value.html` + EPS wyliczone w `docs/validation-thesis.md`),
  spinając obie walidacje — i to właśnie ten przykład ujawnił realny defekt
  (patrz „Defekt znaleziony i naprawiony" niżej).

### Checklist (mirroring WP3/WP4/WP5 acceptance — moja własna numeracja, nie cytat planu)

| # | Co sprawdzono | Status |
|---|---|---|
| 1 | `test_scenarios.py` ≥9, nazwane testy pokryte | **SPEŁNIONE — 14/14** (13 z WP3 + 1 nowy regresyjny z WP5) |
| 2 | `test_scenarios_ai.py` ≥10 | **SPEŁNIONE — 14/14** |
| 3 | `test_valuation_ai.py` ≥8, incl. testy korpusu | **SPEŁNIONE — 25/25** |
| 4 | `select_valuation_multiple` + 3 wzory zgodne z doktryną wyceny (własna historia, nie rynek/branża) | **SPEŁNIONE** — zweryfikowane realnym uruchomieniem |
| 5 | `dossier.py`/`schemas.py` compile-check | **SPEŁNIONE** — `py_compile` 65/65 |
| 6 | frontend `tsc --noEmit` 0; `ScenariosPanel` formatuje przez `lib/format.ts`, zero surowego `toFixed`/`toLocaleString`/`Intl` | **SPEŁNIONE** — exit 0; grep czysty |
| 7 | Money/format (tys.→PLN w matematyce celu, `pl-PL` tylko w UI) | **SPEŁNIONE** — potwierdzone w kodzie |
| 8 | Deferred real-call runbook (`scripts/scenarios_smoke.py`) | **UDOKUMENTOWANE, ODŁOŻONE** |
| 9 | Heurystyka pewności przy nazwanych progach (low/medium/high) | **SPEŁNIONE** — 5 poziomów zweryfikowanych realnym uruchomieniem |
| 10 | Korpus ≥1 miss, każda liczba sourced | **SPEŁNIONE** — SUNTECH = miss, 4 case'y, wszystkie sourced |
| 11 | Pełny in-session test suite, brak regresji na baseline stage TH | **SPEŁNIONE — 176 passed / 0 failed / 0 error / 29 skipped**; `thesis` 13, `thesis_ai` 17, `metrics` 20, `insights` 15 — niezmienione |
| 12 | Żywa próba BR (opcjonalna) | **PRÓBA WYKONANA — ODŁOŻONE** (proxy 403, jak w stage TH) |

---

## Scenariusze — trzy archetypy mnożników (realne uruchomienie, nie przepisane liczby)

Dla każdego z trzech mnożników sektorowych zbudowano `ScenarioInputs` ręcznie
(jak `tests/test_scenarios.py`) i URUCHOMIONO `build_scenario_set` w tej sesji
(`python3` bezpośrednio, nie testy — patrz transkrypt w historii sesji).

### C/Z — przemysł (industrial)
EPS 2,50 zł; bieżący kurs 25,00 zł; własna historia C/Z: q1=11,0 / mediana=14,0
/ q3=17,0 (n=8).

| Scenariusz | p | mnożnik docelowy | cena docelowa | potencjał |
|---|---|---|---|---|
| negatywny | 0,25 | 11,0 (dolny kwartyl) | 27,50 zł | +10,0% |
| bazowy | 0,50 | 14,0 (mediana) | 35,00 zł | +40,0% |
| pozytywny | 0,25 | 17,0 (górny kwartyl) | 42,50 zł | +70,0% |

Wartość oczekiwana ważona: **35,00 zł (+40,0%)** = 0,25×27,5 + 0,50×35,0 + 0,25×42,5.

### C/WK — finanse (finance)
Wartość księgowa 500 000 tys. zł; 10 000 000 akcji → BVPS 50,00 zł; kurs 50,00 zł;
własna historia C/WK: q1=0,80 / mediana=1,00 / q3=1,40 (n=6).

| Scenariusz | p | mnożnik docelowy | cena docelowa | potencjał |
|---|---|---|---|---|
| negatywny | 0,25 | 0,80 | 40,00 zł | −20,0% |
| bazowy | 0,50 | 1,00 | 50,00 zł | 0,0% |
| pozytywny | 0,25 | 1,40 | 70,00 zł | +40,0% |

Wartość oczekiwana ważona: **52,50 zł (+5,0%)**.

### EV/EBITDA — energetyka/surowce (energy)
EBITDA TTM 100 000 tys. zł; dług netto 50 000 tys. zł (`net_cash` = −50 000);
10 000 000 akcji; kurs 50,00 zł; własna historia EV/EBITDA: q1=4,0 / mediana=6,0
/ q3=8,0 (n=5).

| Scenariusz | p | mnożnik | EV implikowane | equity implikowane | cena docelowa | potencjał |
|---|---|---|---|---|---|---|
| negatywny | 0,25 | 4,0 | 400 mln | 350 mln | 35,00 zł | −30,0% |
| bazowy | 0,50 | 6,0 | 600 mln | 550 mln | 55,00 zł | +10,0% |
| pozytywny | 0,25 | 8,0 | 800 mln | 750 mln | 75,00 zł | +50,0% |

Wartość oczekiwana ważona: **55,00 zł (+10,0%)**.

Realny narrative bazowy (skopiowany z live-uruchomienia, nie przepisany ręcznie):

> „Mnożnik wraca do środka do poziomu „mediana własnej historii” (EV/EBITDA 6)
> przy utrzymanym wyniku — cena docelowa 55 zł, +10% wobec bieżącego kursu 50 zł."

**Kontrola spójności prawdopodobieństw:** we wszystkich trzech przypadkach
Σp = 0,25+0,50+0,25 = **1,00 dokładnie** (nie tylko |Σ−1|≤0,01) —
`test_probabilities_sum_to_one`, zweryfikowane.

**Kontrola wyboru mnożnika wg sektora** (`test_multiple_selection_by_sector`):
finance/realestate→C/WK, energy→EV/EBITDA, pozostałe (industrial/tech/consumer/
biotech_med/other)→C/Z — wywiedzione z `malik.py` (`entry_rule.valuation` ∩
`applicable_criteria`), **bez** drugiej twardo-zakodowanej mapy sektorów.

**Monotoniczność:** we wszystkich trzech przypadkach potencjał negatywny ≤
bazowy ≤ pozytywny (kwartyle q1≤mediana≤q3 przekładają się wprost na
uporządkowanie cen) — `test_negative_base_positive_ordering`.

---

## Luki danych — brak fabrykacji (realne uruchomienie)

### Brak sterownika mnożnika I brak fallbacku C/Z
Energetyka bez EBITDA TTM i bez EPS/historii C/Z (`pe_history={}`):
`_resolve_multiple` próbuje najpierw EV/EBITDA (zawodzi — brak EBITDA), potem
fallback C/Z (zawodzi też — brak EPS/historii), więc zwraca `"cz"` jako
**etykietę nominalną** (nie dowód, że dane C/Z istnieją) z PODWÓJNĄ notatką o
luce. Wynik: `valuation_multiple` = `"cz"`, ale WSZYSTKIE ceny docelowe =
`None`, `weighted_expected_price` = `None`. Każdy scenariusz niesie oznakowaną
lukę w `assumptions` (prefiks „Luka danych: "). Zero zmyślonych liczb —
potwierdzone fabrication-guardem (`scenarios.prose_numbers(ss) - allowed ==
set()`).

Realny narrative bazowy (live): „Mnożnik wraca do środka: **C/Z** miałby
wrócić do poziomu „mediana własnej historii”, ale brak danych do wyznaczenia
ceny docelowej (luka danych — patrz założenia)." — silnik nazywa mnożnik,
który PRÓBOWAŁ użyć (C/Z, ostatni fallback), nie ten, który był preferowany
(EV/EBITDA) — subtelne, ale uczciwe: żadna z dwóch prób danych nie istniała.

### Fallback EV/EBITDA → C/Z (sterownik brakuje, ale własna historia C/Z jest)
Energetyka bez EBITDA TTM, ale z EPS 2,0 + historią C/Z (q1=8/mediana=10/q3=12,
n=7), kurs 20,0 zł: silnik PRZEŁĄCZA się na C/Z (`valuation_multiple ==
"cz"`), cena bazowa = 10,0×2,0 = **20,00 zł** (0,0% potencjału — kurs też 20 zł
w tym przykładzie), a fallback jest NAZWANY wprost w `assumptions`: „Uwaga:
Brak danych dla mnożnika EV/EBITDA — użyto własnej historii C/Z (fallback)." —
nigdy cichy.

---

## Defekt znaleziony i naprawiony w tej sesji (WP5)

Podczas budowania dodatkowego, bardziej „fixture'owego" przykładu — scenariusza
złożonego z PRAWDZIWYCH liczb fixture'a DEC (`br_indicators_value.html`: własna
historia C/Z mediana 11,35 / q1 10,78 / q3 11,85, n=8; EPS 2,545 zł z
`docs/validation-thesis.md`, TTM zysk netto 26 892 tys. / 10 566 435 akcji) —
silnik **rzucał `TypeError`**. To ten sam fixture, który stage TH już
udokumentowała jako niosący EPS/własną historię, ale **bez kursu**
(„fixture profile NIE zawiera kursu, więc krocząca C/Z jest niepoliczalna",
`docs/validation-thesis.md`). Ten sam brak kursu, podany do
`scenarios.build_scenario_set`, ujawnił lukę, której WŁASNY zestaw 13 testów
WP3 nie ćwiczył — żaden z trzech archetypów (`cz_inputs`/`cwk_inputs`/
`ev_ebitda_inputs`) łączy „cena docelowa policzalna" z „`current_price=None`"
jednocześnie.

**Przyczyna.** `_build_scenario` (`services/scenarios.py`) rozstrzygał
ścieżkę „oznakowana luka" TYLKO warunkiem `target_price is None or mult_value
is None`. Gdy `target_price` BYŁO policzalne (EPS/book_value/EBITDA znane), a
`current_price` = `None`, kod szedł ścieżką „wyceniony scenariusz" i próbował
sformatować `upside` (poprawnie `None` z guardu `_upside()`) przez
`_fmt_signed()`/`_fmt()` — obie funkcje zakładają liczbę i rzucały
`TypeError: type NoneType doesn't define __round__ method`. **Wpływ w
produkcji:** spółka z policzalnym EPS/wartością księgową/EBITDA, ale BEZ
żadnej ceny (np. wszystkie źródła kursu zawiodły w danym odświeżeniu, albo
świeży debiut) wywaliłaby CAŁY endpoint `/api/companies/{ticker}` (`dossier.py`
woła `build_scenario_set` bezwarunkowo), nie tylko sekcję scenariuszy.

**Naprawa (minimalna, zgodna z regułą „nigdy nie fabrykuj").** Dodano gałąź w
`_build_scenario`: gdy `current_price is None`, narrative pomija porównanie do
kursu i dodaje jawną etykietę luki („Luka danych: brak bieżącego kursu —
potencjału (upside) wobec aktualnej ceny nie wyznaczono."); `implied_upside_pct`
zostaje `None` (bez zmian — było poprawne), `target_price` nadal policzone
(poprawnie — cena docelowa nie zależy od kursu bieżącego). Gałąź z kursem
obecnym jest bajt-w-bajt niezmieniona (istniejące 13 testów WP3 nie mogło
zareagować na tę zmianę).

**Dowód (nowy test, zielony).** `test_missing_current_price_labels_gap_no_crash`
w `tests/test_scenarios.py`: buduje dokładnie ten przypadek (EPS znane,
`current_price=None`) i asertuje `target_price == 35.0`,
`implied_upside_pct is None`, `weighted_expected_price == 35.0`,
`weighted_expected_upside_pct is None`, etykieta luki obecna w
`assumptions`/`narrative`, fabrication-guard nadal czysty. Pełny
`test_scenarios.py` po naprawie: **14/14** (było 13/13, `python3 -m
tests.test_scenarios` bezpośrednio potwierdzone). Cały test suite po naprawie
ponownie zielony: **176 passed / 0 failed / 0 error / 29 skipped** (było 175
przed tym testem) — zero regresji gdzie indziej; `py_compile` 65/65
(niezmienione); `tsc --noEmit` exit 0 (frontend nieruszany tą zmianą).

To odkrycie jest dokładnie tym, po co jest niezależna weryfikacja
fresh-context w WP5 — analogicznie do defektu wiersza „Dywidenda" znalezionego
w post-stage-review etapu TH (`docs/validation-thesis.md`), tylko tu defekt
był w KODZIE (crash), nie w dokumentacji, więc naprawiono kod + dodano
regresyjny test zamiast tylko poprawić opis.

---

## Agent wyceny potencjału — próg pewności (realne uruchomienie, no-key fallback)

Ten sam zestaw scenariuszy (bazowy = +40% potencjału, identyczny w każdym
wierszu) puszczony przez `valuation_ai.assess_potential(..., settings=
SimpleNamespace(anthropic_api_key=None))` z różną głębokością pokrycia:

| Przypadek | wskaźniki kluczowe | n własnej historii | `confidence.level` | `potential.value_pct` |
|---|---|---|---|---|
| < 3 wskaźników | 2 | 8 | **low** | 40,0 |
| n=0 mimo częściowego pokrycia | 0 | 0 | **low** | 40,0 |
| pokrycie środkowe (3–4) | 3 | 8 | **medium** | 40,0 |
| ≥5 wskaźników, ale n<4 | 6 | 3 | **medium** | 40,0 |
| ≥5 wskaźników I n≥4 | 6 | 8 | **high** | 40,0 |

Potwierdza dokładnie progi z planu §WP4a (`_HIGH_KEY_INDICATORS=5`,
`_STABLE_HISTORY_N=4`, `min_key_indicators=3` z profilu Malika). `potential`
jest niezależny od pewności (zawsze = `weighted_expected_upside_pct` w
ścieżce deterministycznej — tu 40,0% w każdym wierszu, bo scenariusz bazowy
jest identyczny; różni się tylko pokrycie danych, czyli TYLKO `confidence`).
Wszystkie 5 progów pokrywają też `tests/test_valuation_ai.py`
(`test_confidence_low_*`, `test_confidence_medium_*`, `test_confidence_high_*`)
— 25/25 zielone.

**Renormalizacja prawdopodobieństw po scenariuszu zdarzeniowym**
(`test_probability_renormalisation_after_event_scenario`, ćwiczona przez
`StubTransport`, część 14/14 zielonych w `test_scenarios_ai.py`): model dodaje
scenariusz `event` i zwraca wagi [0,2 / 0,4 / 0,2] + 0,4 dla eventu (Σ=1,2);
silnik renormalizuje do Σ w granicach ≤0,01 od 1,0, scenariusz zdarzeniowy
PRZETRWAŁ w wyniku i **niesie `target_price: null`** — scenariusze zdarzeniowe
nigdy nie dostają ceny docelowej (silnik AI nie wymyśla wyceny dla
katalizatora, tylko prawdopodobieństwo/narrację/horyzont — plan §WP3b: „event
scenarios carry no target price").

---

## Korpus WorkedCase wzbogacony (WP4b) — brak survivorship bias

`strategies/cases.py` `CORPUS` (leniwie budowany, PEP 562 `__getattr__`,
`test_corpus_is_lazy_and_import_pure` zielony) niesie TERAZ 4 case'y (było 2 w
stage TH: DGN, SNT):

| Ticker | `outcome` | Sourced liczby (przykłady, cytowalne) | Rola |
|---|---|---|---|
| DGN | hit | „+2500% w 5 lat" (≈60 mies.) [DGN, analiza Malika 2025-09-18] | zweryfikowany catch |
| OPTEX | `""` (wzorzec wejścia) | C/Z ~12 trailing, prognoza <10 [F][M1] | wzorzec marginesu bezpieczeństwa; wynik nieskwantyfikowany w źródłach |
| SUNTECH | **miss** | wejście ~2,40 zł [F]; katalizator (nowe kontrakty) się nie zmaterializował | **guard przed survivorship bias** |
| SNT | `""` (placeholder) | brak liczb — atrybucja do Malika NIEzweryfikowana | nasienie kalibracyjne, jawnie oflagowane |

- **≥1 miss potwierdzony:** `test_corpus_has_documented_miss` — SUNTECH,
  `sources`/`citation` obecne (nie goły claim).
- **Każda liczba sourced:** `test_corpus_numbers_are_all_sourced_no_bare_fundamentals`
  — zero zrekonstruowanych fundamentów (`case.inputs.insights.key_indicators
  == []` dla każdego case'a), każdy numer żyje wyłącznie w
  `sources`/`citation`/`gaps`.
- **Cytowalne w fabrication-guardzie:** `test_corpus_enriched_multiples_and_durations_are_citable`
  potwierdza, że **2500,0 / 60,0 / 12,0 / 10,0 / 2,4** (DGN repricing %, DGN
  horyzont w miesiącach, OPTEX C/Z wejście, OPTEX C/Z prognoza, Suntech cena
  wejścia) są w zbiorze `scenarios_ai.collect_corpus_numbers(CORPUS)` — więc
  scenariusz/wycena AI MOŻE je zacytować (traceable), nigdy zmyślić.
- **`evaluate_case` nadal działa** na wszystkich 4 case'ach → `insufficient_data`
  (uczciwa konsekwencja braku fundamentów z epoki wejścia w sandboxie, NIE
  awaria silnika) — `test_evaluate_case_runs_on_enriched_cases`.
- **`test_thesis_ai.py` nadal 17/17** — kontrakt niepustego domyślnego
  `CORPUS` niezmieniony mimo wzrostu z 2 do 4 case'ów.

---

## Walidacja live — próba w tej sesji (ponowne potwierdzenie braku egressu)

Scenariusze/wycena nie dodają nowych źródeł scrapowania — konsumują pola już
policzone przez wcześniejsze fazy. Pełna „walidacja live" tego POZIOMU
wymagałaby więc jednocześnie DB/FastAPI (odłożone) I egressu. Mimo to, zgodnie
z planem („AT MOST a few polite ones… no archiwum pagination"), wykonano
JEDNĄ grzeczną próbę w tej sesji, przez `app.scrapers.http.fetch` — dokładnie
tą samą ścieżką co produkcja, bez omijania modułu:

```
fetch("https://www.biznesradar.pl/notowania/DEC", timeout=8)
→ FetchBlockedError: Giving up … after 3 attempts (network error:
  ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed:
  403 Forbidden')))
```

**Wynik: BRAK EGRESSU, potwierdzone ponownie** — identyczne z ustaleniem
stage TH („Proxy zwraca 403 Forbidden na CONNECT do KAŻDEGO hosta"). Backoff
wewnętrzny modułu wykonał swoje 3 próby (wbudowane zachowanie
`scrapers/http.py`, NIE ręczne ponawianie) w ~15 s, po czym poddano się — zero
dalszych prób, zero archiwum, zero paginacji.

`mcp__workspace__web_fetch` (narzędzie agenta) NIE było ponownie próbowane w
tej sesji: stage TH już ustaliła i udokumentowała (`docs/validation-thesis.md`
§"Walidacja live"), że to narzędzie zwraca markdown, nie HTML, więc parsery
BeautifulSoup i tak nie ruszają — a scenariusze/wycena nie parsują ŻADNEJ
nowej strony, więc powtórzenie tej samej próby nie dodałoby żadnej informacji
specyficznej dla stage SC. Prawdziwa „walidacja live" TEGO etapu to
`scripts/scenarios_smoke.py <TICKER>` na maszynie użytkownika (DB + klucz +
egres) — patrz runbook niżej.

**Grzeczność:** 1 żądanie w tej sesji (przez `scrapers/http.py`, z jego
wbudowanym jitter/backoff — 3 próby wewnętrzne, ~15 s), 0 ręcznych ponowień,
archiwum notowań nietknięte, 0 paginacji `,N`.

---

## Testy — dokładne liczby (in-session, ta sesja)

Shim zbudowany w `/tmp` (fałszywy moduł `pytest`: `fixture`/`mark.parametrize`/
`raises`/`approx`/`skip` + fałszywy `tests.conftest` w miejsce prawdziwego,
który importuje FastAPI; repo nietknięte) + bezpośredni import każdego modułu
testowego (`tests.<nazwa>`), zamiast polegać na auto-discovery pytest.

| Plik | pass | skip | fail | error | uwaga |
|---|---|---|---|---|---|
| `test_thesis.py` | 13 | 0 | 0 | 0 | baseline stage TH niezmieniony |
| `test_thesis_ai.py` | 17 | 0 | 0 | 0 | baseline niezmieniony; `CORPUS` 2→4 case'y bez wpływu |
| `test_metrics.py` | 20 | 0 | 0 | 0 | baseline niezmieniony |
| `test_insights.py` | 15 | 0 | 0 | 0 | baseline niezmieniony |
| `test_forecast.py` | 5 | 0 | 0 | 0 | |
| `test_biznesradar_parser.py` | 33 | 6 | 0 | 0 | skip = `real_br_*.html` nigdy nienagrane (genuine, plik po pliku sprawdzone) |
| `test_http.py` | 6 | 0 | 0 | 0 | |
| `test_stooq.py` | 8 | 0 | 0 | 0 | |
| `test_forum.py` | 3 | 3 | 0 | 0 | skip = testy wymagające FastAPI `TestClient` |
| `test_yahoo.py` | 3 | 2 | 0 | 0 | skip = testy wymagające FastAPI `TestClient`/SQLAlchemy `db` |
| **`test_scenarios.py` (WP3+WP5)** | **14** | 0 | 0 | 0 | 13 z WP3 + 1 regresyjny z WP5 (≥9 wymagane) |
| **`test_scenarios_ai.py` (WP3)** | **14** | 0 | 0 | 0 | ≥10 wymagane |
| **`test_valuation_ai.py` (WP4)** | **25** | 0 | 0 | 0 | ≥8 wymagane, incl. testy korpusu |
| `test_api_phase1.py` | 0 | 12 | 0 | 0 | cały plik wymaga FastAPI `TestClient` |
| `test_api_phase3.py` | 0 | 6 | 0 | 0 | cały plik wymaga FastAPI `TestClient` |
| `test_migrations.py` | — | — | — | — | **COLLECTION ERROR** — importuje `sqlalchemy`/`alembic` wprost |
| `test_refresh_prices.py` | — | — | — | — | **COLLECTION ERROR** — importuje `sqlalchemy` wprost |
| **RAZEM (pliki importowalne)** | **176** | **29** | **0** | **0** | + 2 collection error (0 testów z tych 2 plików) |

`py_compile`: **65/65** plików (cały `backend/`, w tym `alembic`/`tests`/
`scripts`); **41/41** dla samego `app`+`scripts` (ten sam podzbiór co bazowa
liczba po WP4, niezmieniona). `tsc --noEmit`: **exit 0** (frontend,
`ScenariosPanel.tsx` + `types.ts` wliczone; grep po `toFixed`/`toLocaleString`/
`Intl.` w `ScenariosPanel.tsx` — zero trafień).

**Metodologia różni się nieznacznie od wcześniejszych sesji tej stage'y** (nie
w wyniku, tylko w ziarnistości): zamiast całkowicie pomijać pliki wymagające
`client`/`db` na poziomie CAŁEGO pliku, ten shim WSTRZYKUJE fałszywy
`tests.conftest` do `sys.modules` PRZED importem, więc pliki bez bezpośredniego
importu SQLAlchemy/FastAPI na górze (`test_api_phase1.py`, `test_api_phase3.py`,
`test_forum.py`, `test_yahoo.py`) importują się poprawnie, a KAŻDY test
osobno dostaje SKIP z konkretnym powodem („needs FastAPI TestClient"), zamiast
całego pliku oznaczonego jako nieimportowalny. Wynik końcowy jest ten sam
(odłożone na maszynę użytkownika), tylko raportowanie jest drobniejsze i
bardziej przejrzyste — stąd 29 skipped tutaj vs. inny podział skip/deferred w
poprzednich sesjach tej samej stage'y. Pliki z bezpośrednim `import
sqlalchemy`/`import alembic` NA GÓRZE (`test_migrations.py`,
`test_refresh_prices.py`) i tak nie importują się w ogóle niezależnie od tej
techniki — to jedyne dwa prawdziwe „collection errors".

---

## Reguła fixture-first — potwierdzona

Wszystkie trzy nowe pliki testowe (`test_scenarios.py`, `test_scenarios_ai.py`,
`test_valuation_ai.py`) używają WYŁĄCZNIE ręcznie budowanych `ScenarioInputs`/
`StubTransport` — **zero** żywych żądań HTTP w samym test suite. Jedyne żywe
żądanie w tej sesji (opisane wyżej) było osobną, ręczną próbą walidacyjną
POZA test suite, zgodną z planem („AT MOST a few polite ones… no archiwum
pagination").

## Braki / odłożone na maszynę użytkownika (jawnie, nic nie ukryte)

1. **`cd backend && pytest`** — pełny DB/API suite (24 testy w
   `test_api_phase1`/`test_api_phase3`/`test_migrations`/`test_refresh_prices`
   + pełne wiring `dossier.py`→`scenarios`/`valuation` blocks pod Postgresem).
2. **`cd frontend && npm run build`** — produkcyjny build (tu sprawdzony
   tylko `tsc --noEmit`).
3. **`ANTHROPIC_API_KEY=… python scripts/scenarios_smoke.py <TICKER>`** —
   realna iteracja Claude dla scenariuszy I wyceny potencjału (ścieżka AI
   ćwiczona tu WYŁĄCZNIE przez `StubTransport`).
4. **Żywa walidacja BR** (≥1 prawdziwy ticker przez cały pipeline
   scraper→dossier→scenariusze) — wymaga jednocześnie DB i egressu, których
   sandbox nie ma; próba egressu wykonana i udokumentowana wyżej.
5. **Korpus WorkedCase** — DGN/OPTEX/SUNTECH entry-era fundamenty nadal
   nieodtwarzalne w sandboxie (ten sam gap co stage TH); uzupełnienie przez
   `scripts/validate_thesis.py` na maszynie użytkownika.

---

## Ścieżka silnika (przypomnienie)

Ten dokument = ścieżka DETERMINISTYCZNA (`build_scenario_set` /
`_build_deterministic_valuation`), zweryfikowana realnym uruchomieniem w tej
sesji, plus jeden realny defekt znaleziony I naprawiony (patrz wyżej). Ścieżka
AI (`scenarios_ai.simulate_scenarios` / `valuation_ai.assess_potential` z
kluczem) — wyłącznie `StubTransport` w testach; realne API i pełna ścieżka
DB/API odłożone na maszynę użytkownika (patrz „Braki" wyżej).
