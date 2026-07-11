# Walidacja silnika tezy — DGN/SNT historycznie + sanity bieżących spółek

Stage TH / WP4 (history archived in `docs/archive/plans/plan-stage-thesis.md`). Cel: sprawdzić, czy kryteria
złapałyby dawne trafienia Malika (Digital Network, wczesny Synektik) i czy
silnik czyta rozsądnie bieżące spółki różnej wielkości — **z uczciwym opisem
tego, na co dane pozwalają, a na co nie**. Data: 2026-07-08.

## Metoda i realia środowiska (uczciwie, bez papierowania)

- **Ścieżka silnika: DETERMINISTYCZNA.** Walidacja uruchamia
  `thesis.build_thesis(..., MALIK)`. Bez klucza `ANTHROPIC_API_KEY` (domyślnie
  w sandboxie) refiner WP2b jest przezroczystym pass-throughem
  (`engine: "deterministic"`); ścieżkę AI ćwiczy WYŁĄCZNIE `StubTransport`
  w `tests/test_thesis_ai.py` (17/17). Realne wywołanie API (`scripts/thesis_ai_smoke.py`)
  jest odłożone na maszynę użytkownika.
- **Ścieżka DB/API odłożona.** Sandbox nie ma Postgresa/SQLAlchemy/Pydantica,
  więc `dossier.build_dossier` + `api/schemas` nie są tu wykonywane. Wejścia
  składane są **czystym pipeline'em** (parsery → `fields.py` → `metrics.py` →
  `insights.py` → `build_thesis`), dokładnie odtwarzającym *czystą* połowę
  `dossier.py` — patrz `scripts/validate_thesis.py`.
- **Sandbox Python/proxy: BRAK egressu.** Proxy zwraca `403 Forbidden` na CONNECT
  do KAŻDEGO hosta (także `example.com`), więc `biznesradar.pl` jest nieosiągalny
  przez `app/scrapers/http.py` — kod scrapera aplikacji i `scripts/validate_thesis.py`
  **nie wykonały żadnego żądania**; czysty pipeline ćwiczono na fixturach (scenariusz
  „no egress → fallback na fixtury" z planu §Sandbox / testing reality).
- **KOREKTA 2026-07-08 (WP4b): agentowy `mcp__workspace__web_fetch` JEDNAK dociera
  do BR.** Wcześniejsza wersja tego dokumentu (i wpis CHANGELOG WP4) twierdziła, że
  web_fetch „też się nie łączy (timeout)" — to było **błędne**. Narzędzie łączy się
  (HTTP 200, podąża za redirectem slug SNT→SYNEKTIK), ale zwraca **oczyszczoną
  ekstrakcję markdown/tekst, nie surowy HTML** — więc parsery BeautifulSoup nie mają
  na czym pracować (pełen dowód: sekcja „Walidacja live" niżej). W tej sesji wykonano
  **2 realne żądania web_fetch** (feasibility probe), nie 0.
- **Co realnie było dostępne:** commitowane fixtury w `backend/tests/fixtures/`
  są **syntetyczne** (struktura wierna markупowi referencyjnego scrapera) i
  modelują **DECORA (DEC)** — mała spółka „materiały budowlane". Na nich
  przepuszczono **pełny** pipeline z prawdziwie *parsowanych stron* (nie ręcznie
  budowanych dictów). Archetypy small/mid/large oraz weak/biotech to ręcznie
  budowane wejścia z `tests/test_thesis.py` (jawnie oznaczone).
- **Odłożone na maszynę użytkownika (gdzie działa egress):** realne pobranie
  DGN/SNT i kilku żywych spółek —
  `cd backend && python scripts/validate_thesis.py DGN` (kolejno SNT, np. DNP/PKN,
  DEC). Harness pobiera **po slug'u**, 6 stron/spółkę, z cache'em na dysku.

### Status kryteriów akceptacji (uczciwie)

| # | Kryterium | Status |
|---|---|---|
| 1 | ≥4 bieżące tickery, każda liczba skrzyżowana z BR | **CZĘŚCIOWO / ODŁOŻONE** — 1 realnie parsowana spółka (DEC, fixture) skrzyżowana w całości. Próba live przez `web_fetch` **wykonana i udokumentowana** („Walidacja live"): narzędzie dociera do BR, ale zwraca non-HTML → parsery nie ruszają, więc ≥4 żywe tickery pozostają odłożone (teraz z precyzyjnym powodem, nie „brak egressu"). Porównywalność między wielkościami pokazana kontrolowaną wrażliwością na rozmiar (realne outputy). |
| 2 | Porównywalność (moloch dostaje karę; mały + niskie własne C/Z + gotówka netto → atrakcyjny) | **SPEŁNIONE** — realne outputy, ten sam zestaw wejść, przełączony tylko rozmiar. |
| 3 | Werdykt DGN/SNT + lista braków, bez zmyślonych liczb | **SPEŁNIONE**. |
| 4 | Grzeczność (archiwum str. 1, mały wolumen, brak paginacji, quirks nie re-derywowane) | **SPEŁNIONE** — 2 żądania `web_fetch` (feasibility probe), ≥3 s odstęp, archiwum nietknięte, 0 paginacji, quirks followed; harness aplikacji (`http.py`) nietknięty. Szczegóły w „Walidacja live". |
| 5 | WorkedCase DGN/SNT ładują się i `evaluate_case` na nich działa | **SPEŁNIONE** (oba → `insufficient_data`, `matches=True`). |

---

## Walidacja live (in-session, web_fetch) — próba i wynik feasibility

**Wynik: NIEWYKONALNA istniejącym pipeline'em.** Agentowe narzędzie
`mcp__workspace__web_fetch` **dociera** do biznesradar.pl (koryguje wcześniejszy
błędny zapis „timeout"), ale zwraca **oczyszczoną ekstrakcję markdown/tekst, a nie
surowy HTML**. Parsery `app/scrapers/biznesradar.py` to parsery BeautifulSoup i
szukają struktury, której w markdownie NIE MA. Feasibility-gate z kontraktu
(„parsery nie ruszają ORAZ nie da się odzyskać struktury → STOP") jest spełniony;
Job 2 zatrzymany na gruncie HTML. Deferral z acceptance #1 **stoi — z precyzyjnym
powodem**: nie „brak egressu", lecz „web_fetch dociera, ale zwraca nieużyteczny
non-HTML".

### Dowód (odtwarzalny bez ponownego pobierania)

Artefakty: `backend/tests/fixtures/live-20260708/SNT_profile.md` (pełna ekstrakcja
profilu) + `SNT_income_q.excerpt.md` (excerpt rachunku wyników + liczniki grep).
Pliki `.md` są **obojętne dla testów fixture** (ładują po dokładnej nazwie
`*.html`, nie globem katalogu).

- **Zero struktury HTML.** `grep -c` po PEŁNEJ ekstrakcji strony rachunku wyników
  (72 742 znaków / 114 linii): `report-table`=0, `data-field`=0,
  `span class="value"`=0, `<table`/`<tr`/`<td`=0.
- **Parsery zwracają pustkę / błąd** (uruchomione realnie na zapisanym markdownie):
  - `parse_profile(SNT_profile.md, "SNT")` → **wszystkie pola `None`**: `name`,
    `shares_outstanding` (strona: 8 529 129), `market_cap` (3 213 775 722),
    `enterprise_value` (3 234 628 722), `sector` (Biotechnologia), `price` (376.80),
    `slug`. Dane SĄ w markdownie widoczne — ale parser czyta `<td>/<th>` i
    `<meta itemprop="price">`, których tam nie ma.
  - `parse_report_table(..., "Q")` → **`ParseError: No report table found on page.`**
    Pipeline pada na PIERWSZYM etapie.
- **Dwie nieodwracalne straty** (widoczne w excerpt):
  1. **Brak kodów `data-field`** (stabilna tożsamość wiersza wg quirks ledger). Kod
     (`IncomeRevenues`) przeżywa TYLKO w URL-u linku porównania sektorowego i tylko
     dla wierszy, które taki link mają. Dopasowanie po samych (dwuznacznych,
     zduplikowanych między sekcjami) etykietach re-uruchamia dokładnie te pułapki,
     które ledger każe omijać: `IncomeGrossProfit`=„Zysk ze sprzedaży", `cz` vs
     `czo`, „Marża zysku brutto"=pretax.
  2. **Wartość + zmiana k/k + `~branża` sklejone w JEDNEJ komórce**
     (`6 798   k/k +247.72%~branża +54.06%`) — w HTML rozdzielone `span.value` +
     rodzeństwo; markdown je zlepia, więc każda komórka wymaga re-segmentacji.

### Dlaczego NIE budujemy obejścia (świadoma decyzja)

Odzyskanie tego wymagałoby **nowego, dedykowanego parsera markdown** (re-segmentacja
każdej komórki, rekonstrukcja tożsamości pól z URL-i/etykiet, ponowna implementacja
wykrywania nagłówków okresów, pomijania kolumny TTM, dedupu powtórzonych kolumn,
pułapki free-float…). To: (a) **obejście** — kontrakt wprost zabrania „fabrykowania
workaroundu"; (b) łamie CLAUDE.md („zmiany parsera wymagają zielonych testów
fixture"); (c) **omija sam etap parsera, który walidujemy**; (d) ręczne przepisywanie
liczb = ryzyko fabrykacji, którego zasady uczciwości zabraniają. Parsera **nie
hot-fixowano** — ewentualny bespoke-parser to osobna, przetestowana zmiana na
przyszłość, nie WP4b.

### Log żądań (grzeczność zreplikowana ręcznie)

Decyzja orkiestratora (wdrożona): reguła CLAUDE.md „ALL HTTP przez
`scrapers/http.py`" rządzi **kodem scrapera aplikacji, który pozostał nietknięty**;
dla TEJ walidacji w-sesji pobranie stron BR sankcjonowanym `mcp__workspace__web_fetch`
było dozwolone POD WARUNKIEM ręcznej replikacji grzeczności (≥3 s odstęp, budżet
≤24 żądania, archiwum tylko strona 1, brak paginacji, 1 retry max, log każdego
żądania).

| # | Czas (UTC) | URL | Wynik |
|---|---|---|---|
| 1 | 2026-07-08 ~08:29 | `/notowania/SNT` | 200, redirect →`/SYNEKTIK`, markdown |
| 2 | 2026-07-08 08:29:28 | `/raporty-finansowe-rachunek-zyskow-i-strat/SYNEKTIK,Q` | 200, markdown (72 742 zn.) |

- **Razem: 2 żądania** (budżet ≤24). Feasibility-gate padł na req. 2 → DALSZYCH stron
  ani tickerów NIE pobierano („debugging never means fetch more"). 0 retry (oba 200).
- **Odstęp ≥3 s** wymuszony `sleep` między żądaniami (plus czas rozumowania).
- **Archiwum notowań: NIE dotknięte** → zero ryzyka paginacji `,N`. Strona raportu po
  slug'u (pułapka redirectu `,Q` — suffix zachowany w żądaniu). Quirks ledger
  **followed, nie re-derywowany**.

---

## Bieżące spółki — sanity

### DEC (Decora) — realnie parsowany fixture (wartości syntetyczne)

Pełny pipeline nad *parsowanymi stronami* fixture'a (`profile` + `income_q` +
`balance_q` + `indicators_value` + `indicators_profitability` + `dividends`).

- **`entry_quality` = `neutral`** („Neutralny punkt wejścia w analizę").
  Rozmiar: `small` (kap. raportowana 258 877 658 zł < 1 mld); branża → grupa
  `industrial`; prescore **7/8**.
- **Dlaczego neutral, a nie attractive:** fixture `profile` **nie zawiera kursu**,
  więc krocząca C/Z jest niepoliczalna → `pe_vs_history` trafia do „co sprawdzić
  dalej", a NIE jest zmyślana. Reguła `attractive` wymaga dobrej wyceny ORAZ
  sygnału wzrostu ORAZ gotówki netto; bez wyceny silnik **uczciwie wstrzymuje**
  „attractive". `valuation_basis`: „Brak C/Z (spółka nierentowna lub brak kursu)
  — wyceny nie można ocenić; oprzyj tezę na pozostałych sygnałach."
  *Uwaga:* przy realnym pobraniu profil niesie kurs (`meta itemprop="price"`
  lub „Kurs:"), więc żywy DEC miałby policzoną C/Z — tutejsze `neutral` to
  artefakt braku kursu w syntetycznym fixture, a **sama reakcja silnika na lukę
  jest walidowanym zachowaniem**.
- **Mocne strony tezy (kolejność wg wagi):** `gross_margin` (3,0) · `revenue_growth`
  (2,5) · `one_offs` (2,5) · `operating_leverage` (2,0) · `size` (2,0, sweet spot)
  · `debt_load` (1,5) · `roe` (1,5). **Ryzyka:** brak (0 czerwonych flag).
- **Co sprawdzić dalej:** `pe_vs_history` (luka danych) + stałe luki strategii:
  `catalyst`, `backlog`, `management`, `cashflow_quality`, `thesis_recheck`.

**Liczby skrzyżowane z fixture (silnik ↔ strona):**

| Pozycja | Wartość silnika | Źródło | Surowa strona | Odchyłka |
|---|---|---|---|---|
| Kapitalizacja | 258 877 658 zł | profil „Kapitalizacja" (raportowana, autorytatywna) | `258 877 658` | 0 |
| Liczba akcji | 10 566 435 | profil „Liczba akcji" | `10 566 435` (nie free-float `6 400 000`) | 0 — **pułapka free-float ominięta** |
| Gotówka netto | 22 000 tys. zł | bilans: gotówka 30 000 − dług 5 000+3 000 | `30 000 / 5 000 / 3 000` | 0 |
| TTM zysk netto | 26 892 tys. | Σ 4 ost. kw. (6107+6691+6132+7962) | rachunek wyników | 0 |
| EPS | 2,545 zł | 26 892×1000 / 10 566 435 | — | 0 |
| Krocząca C/Z | `null` | brak kursu w fixture | — | **luka** → verify_next (nie zmyślona) |
| Mediana C/Z (własna) | 11,35 | 8 pkt BR: 12,50·11,80·12·11,50·10,90·11,20·10,40·9,80 | strona wskaźników | 0 |
| Marża brutto | 34,0% (+1,8 p.p.) | kwartały (gross/revenue); zgodna z GPM 34,0 | rentowność | 0 |
| Wzrost przychodów | 12,0% r/r | śr. 2 ost. kw. yoy (10,0 i 14,0) | — | 0 |
| One-offy | 1,1% | \|EBIT 10 000 − zysk ze sprzedaży 9 894\| / 10 000 | — | 0 |
| ROE | 20,4% | wskaźnik ROE (2025Q1) | rentowność | 0 |
| Dywidenda | — (wskaźnik nieoceniany przez tezę dla grupy `industrial`) | tabela dywidend 2023–2025 | `2025/1,20/4,9%` | — (patrz nota) |

**Korekta wiersza „Dywidenda" (weryfikacja świeżym kontekstem, 2026-07-08):**
dane dywidendy **parsują się poprawnie** i zgadzają ze stroną (2023–2025, DPS
1,20 zł, stopa 4,9%) — ale **teza nigdy nie ocenia `dividend` dla grupy
`industrial`**. Root cause: `insights.py` `_GROUP_PLAYBOOK["industrial"]` =
`[gross_margin, revenue_growth, operating_leverage, debt_load, one_offs,
pe_vs_history]`, bez `dividend` (kryterium dywidendy mają tylko grupy finance/
energy/realestate). Więc `spec_dividend()` nie odpala dla DEC (sektor „Materiały
budowlane" → `industrial`), `idx.get("dividend")` jest `None` w `build_thesis`,
a kryterium jest **po cichu pomijane** — w realnym wyjściu tezy DEC NIE MA żadnego
wpisu dywidendy (ani pros, ani cons, ani verify_next; `insights.missing ==
["pe_vs_history"]`). Poprzednia wersja tego wiersza **przypisywała tezie odczyt,
którego nie ma** (zwalidowany cross-check silnik↔strona z odchyłką 0). **Luka
warstwowa (do zanotowania):** kryterium `dividend` w `strategies/malik.py` nie ma
ograniczenia stosowalności sektorowej, a playbook wyklucza dywidendę dla **5 z 8**
grup → realna historia dywidend jest dla tezy **niewidzialna** (brak pro, brak con,
brak flagi verify_next) dla spółek industrial/tech/biotech/consumer/other. To
**istniejące zachowanie `insights.py`, nie wprowadzone przez etap TH.** Czy dodać
dywidendę do kolejnych playbooków, ograniczyć kryterium malik, czy kierować nigdy-
nie-wybrane kryteria do verify_next — **decyzja produktowa dla użytkownika**.

**Pułapki etykiet wskaźników (quirks ledger — potwierdzone, nie re-derywowane):**
`Cena / Wartość księgowa Grahama` NIE zmapowana na `cwk`; `Marża zysku brutto`
(pretax) NIE zmapowana na `gross_margin`; `Cena / Zysk operacyjny` → własny kod
`czo` (nie `cz`); `Jakiś inny wskaźnik` odrzucony. Wszystkie zgodne z sekcją
„BiznesRadar — indicator pages" w `skills/scraper-doctor/SKILL.md`.

**Drobna obserwacja (poza zakresem WP4, do decyzji użytkownika):** w
`insights.py` komentarz marży renderuje „+1.8 p.p." (kropka), a `brief`
„+1,8 p.p." (przecinek) — kosmetyczna niespójność formatowania `pl-PL` w samym
`insights.py`; nie wprowadzona przez WP4 i nie ruszana (wymaga własnego testu
fixture + wpisu CHANGELOG).

**Druga drobna obserwacja (poza zakresem, do decyzji użytkownika):** w
`strategies/malik.py` szablon `size_pro_text` ma zakodowane na sztywno „Mała
spółka ({size})", więc dla small-capa wyrenderowany pro brzmi „Mała spółka (Mała
spółka) — sweet spot strategii…" (duplikacja; dla micro czyta się poprawnie). Ta
sama klasa co niespójność „+1.8 p.p."/„+1,8 p.p." wyżej — kosmetyka, nie ruszana
w tej korekcie (wymaga własnego testu + wpisu CHANGELOG).

### Porównywalność między wielkościami (kara moloch / sweet spot)

Ponieważ egress był zablokowany, porównywalność pokazano **kontrolowaną
wrażliwością na jeden lewar**: TE SAME wejścia (archetyp small profitable
industrial z `tests/test_thesis.py`: C/Z 9,5 vs własna mediana 14,0; rosnąca
marża brutto; gotówka netto; C/Z prognozowane 8,7), przełączany tylko `size_code`.
To realne outputy silnika, nie asercje.

| Rozmiar | `entry_quality` | Czynnik `size` | Racjonale (skrót) |
|---|---|---|---|
| `small` | **attractive** | PRO | „Dobra wycena na tle własnej historii i sygnał wzrostu przy braku długu netto…" |
| `mid` | **neutral** | CON | „Zestaw sygnałów byłby atrakcyjny, ale spółka jest poza sweet spotem strategii…" |
| `large` | **neutral** | CON | jak wyżej (kara sweet spot, spec zasada 9 — „nie lubię spółek typu Orlen") |

→ **Moloch dostaje karę** (identyczne liczby, tylko rozmiar → attractive spada
do neutral), a **mały profitable + niskie własne C/Z + gotówka netto → attractive**.
Kryterium akceptacji #2 pokazane realnymi wyjściami.

Pozostałe archetypy (ręcznie budowane, `tests/test_thesis.py`) domykają kody:

| Archetyp | `entry_quality` | Dlaczego |
|---|---|---|
| weak | **weak** | C/Z 22,0 powyżej własnej mediany 12,0 — „rynek już wycenia poprawę" |
| biotech (cash-burn) | **insufficient_data** | strata, brak C/Z, za mało policzalnych wskaźników |

---

## Historia — DGN i SNT

> Zasada uczciwości (plan §Risks & honesty): fundamenty z daty wejścia mogą być
> niedostępne; głębokość własnej historii C/Z jest tylko taka, jaką pokazuje BR;
> DGN mógł być przemianowany. **Dokumentujemy luki, nie fałszujemy backtestu.**
> Żadna liczba historyczna bez źródła lub etykiety „niedostępne".

### DGN (Digital Network, ex-4fun Media) — werdykt

- **Trafienie ZWERYFIKOWANE:** flaga POS PortalAnaliz 02.2023; własna analiza
  Malika „+2500% w ciągu 5 lat… książkowy przykład" (2025-09-18) — `docs/strategy-malik.md`
  anchors **[DGN][AUT]**. **Cena wejścia „~20 PLN" NIEzweryfikowana** (spec
  §Unverified) → **nie użyta jako liczba**.
- **Czy kryteria by ją oflagowały?** *Jakościowo — spójne* z zasadami: sweet
  spot małych spółek (zasada 9), teza-z-katalizatorem (zasada 7 — pivot na
  cyfrową dystrybucję), sprawozdania-first / wzrost (zasady 2–4). **Mechanicznie
  — NIEDOWODLIWE w sandboxie:** fundamenty z epoki wejścia (własna historia C/Z,
  trend marży brutto, gotówka netto, dynamika przychodów) są **nieodtwarzalne**
  (brak egressu; głębokość danych BR nieznana).
- **WorkedCase → `insufficient_data`** (`matches=True`): 0 z 4 policzalnych
  wskaźników — uczciwa konsekwencja luk, nie porażka silnika. `verify_next`
  wskazuje DOKŁADNIE brakujące nogi: `pe_vs_history`, `gross_margin`,
  `revenue_growth`, `net_cash` + luki strategii (`catalyst`, `backlog`,
  `management`, `cashflow_quality`, `thesis_recheck`). Czynnik `size` (mały,
  sweet spot) się pojawia — źródłowany jakościowo, nie liczbowo.
- **Czego brakuje, by powiedzieć więcej:** fundamenty z daty wejścia; potwierdzenie
  „~20 PLN"; głębokość własnej historii C/Z na BR; katalizator (jakościowy).
  Do uzupełnienia: `python scripts/validate_thesis.py DGN` tam, gdzie działa egress.

### SNT (Synektik) — werdykt

- **Atrybucja NIEzweryfikowana:** brak pierwotnego dokumentu wiążącego Malika z
  wczesnym wejściem w SNT (`docs/strategy-malik.md` §Unverified). **Nie
  traktujemy tego jako trafienia Malika.** SNT występuje w repo tylko jako
  historyczny ticker fixture'ów scrapera (układ kalkulacyjny — `scraper-doctor`).
- **WorkedCase → `insufficient_data`** (`matches=True`): pozycja niesie flagę
  „NIEzweryfikowane" jako pierwszą; to **nasienie kalibracyjne z jawną flagą, nie
  potwierdzony sukces**. Żadnych fundamentów SNT w sandboxie (commitowany fixture
  modeluje DECORA, nie SNT).
- **Czego brakuje:** potwierdzenie atrybucji w źródłach; jakiekolwiek fundamenty SNT.

### Braki (podsumowanie, acceptance #3)

| Element | DGN | SNT |
|---|---|---|
| Fundamenty z daty wejścia | niedostępne (brak egressu) | niedostępne |
| Cena / atrybucja | „~20 PLN" niezweryfikowana | atrybucja do Malika niezweryfikowana |
| Własna historia C/Z (BR) | głębokość nieznana | brak danych |
| Katalizator | jakościowy (pivot na digital) | brak |
| Wynik `evaluate_case` | `insufficient_data` (uczciwie) | `insufficient_data` (uczciwie) |

---

## WorkedCases (acceptance #5)

`strategies/cases.py` — `CORPUS = (DGN, SNT)`. Oba wpisy: częściowy snapshot
z **etykietami źródeł per-pole** (`sources`), oczekiwanym odczytem
(`expected_read = insufficient_data` — uczciwie osiągalny z odtwarzalnych danych)
i **jawną listą braków** (`gaps`). `evaluate_case(MALIK, ·)` uruchamia się na obu
i zwraca `insufficient_data` z `matches[entry_quality] = True`.

- **Cytaty:** DGN → „docs/strategy-malik.md §Filozofia + §Unverified; anchors
  [DGN][AUT][SB]"; SNT → „docs/strategy-malik.md §Unverified — „Synektik (SNT)
  'early' catch — UNVERIFIED"".
- **Decyzja techniczna:** `CORPUS` budowany **leniwie** (module `__getattr__`,
  PEP 562), bo konstrukcja `WorkedCase` dotyka `thesis.ThesisInputs`, a
  `app.services.thesis` importuje pakiet strategii — budowa przy imporcie tworzyła
  cykl (thesis → strategies → cases → thesis). Odłożenie do pierwszego dostępu
  `cases.CORPUS` usuwa cykl; `cases.py` pozostaje import-pure (tylko stdlib).
- **Naprawiony test (minimalnie):** `test_thesis_ai.test_ai_request_payload_carries_inputs_and_profile`
  asertuje `worked_cases == []`, ale wołał `refine_thesis` bez `corpus=` — teraz
  domyślny `cases.CORPUS` jest niepusty, więc przekazano jawnie `corpus=()`
  (ścieżka pustego korpusu). Niepusty domyślny korpus pokrywa
  `test_ai_request_payload_includes_injected_corpus`. Oba pliki testów zielone.

Do przyszłej kalibracji: gdy użytkownik na swojej maszynie zrekonstruuje
fundamenty DGN/SNT (`validate_thesis.py`), te case'y można wzbogacić i podnieść
`expected_read` — dziś honestly puste, bo dane na to nie pozwalają.

---

## Grzeczność (non-negotiable)

- **Harness aplikacji (`scripts/validate_thesis.py`): 0 żądań HTTP** — jego egress
  przez `app/scrapers/http.py` jest zablokowany (jitter per-domena BR 2–4 s, backoff
  ×3, twardy stop `FetchBlockedError`; kod nietknięty). **Osobno**, dla próby live
  (sekcja „Walidacja live"), wykonano **2 żądania sankcjonowanym
  `mcp__workspace__web_fetch`** z ręcznie zreplikowaną grzecznością (≥3 s odstęp,
  budżet ≤24, archiwum nietknięte, 0 paginacji). Łącznie w sesji: **2 realne
  żądania**, nie 0.
- **Archiwum notowań NIE pobierane** (teza nie potrzebuje historii kursu) → zero
  ryzyka paginacji; żadnych stron paginowanych `,N`. Reguła „archiwum tylko
  strona 1" respektowana przez nietykanie jej w ogóle.
- **Quirks ledger FOLLOWED, nie re-derywowane:** strony raportów pobierane po
  `slug` (pułapka redirectu `,Q`→annual); pułapki etykiet wskaźników potwierdzone
  na fixture; cache 24 h realizowany cache'em na dysku (`backend/.cache/validation/`,
  gitignored).
- **Na maszynie użytkownika:** każde `validate_thesis.py TICKER` ≈ 6 stron BR
  (profil + income_q + balance_q + 2× wskaźniki + dywidendy), po slug'u, cache'owane
  — ~6 żądań/spółkę przez ~20–30 s.

## Ścieżka silnika (przypomnienie)

Walidacja = **deterministyczna** (`build_thesis`). AI (WP2b) tylko przez
`StubTransport` w `tests/test_thesis_ai.py` (17/17); realne API i ścieżka DB/API
odłożone na maszynę użytkownika. Pełny `pytest`, migracje i żywe UI — również tam.

---

## Weryfikacja świeżym kontekstem (2026-07-08, po zamknięciu etapu)

Niezależny przebieg weryfikacyjny etapu TH (agenty sonnet, hands-on). Wszystkie
liczby poniżej zweryfikowane praktycznie; **jedyny defekt** to wiersz „Dywidenda"
wyżej (skorygowany).

- **Testy bezpośrednio:** `test_thesis.py` **13/13**, `test_thesis_ai.py` **17/17**;
  `py_compile` **53/53** plików zielone; czystość importu utrzymana (brak
  pydantic/anthropic/fastapi/sqlalchemy/requests po imporcie
  thesis/thesis_ai/strategies), `cases.CORPUS` leniwie buduje DGN+SNT bez cyklu.
- **Korekta niedopowiedzenia z „Stage TH complete".** Że `test_insights`/`test_metrics`
  „cannot run" w sesji to prawda **tylko** dla metody `python3 tests/...`. Z minimalnym
  **shimem pytest** (fixture/parametrize/raises/approx + podrobione czyste helpery
  conftest, zbudowany w `/tmp`, repo nietknięte) uruchomiły się też w sandboxie:
  `test_metrics` 20/20, `test_insights` 15/15, `test_forecast` 5/5,
  `test_biznesradar_parser` 33 + 6 skip (skipy prawdziwe — fixtury `real_br_*.html`
  nigdy nienagrane), `test_http` 6/6, `test_stooq` 8/8, `test_forum` 3 + 3 skip
  (potrzebują `client`), `test_yahoo` 3 + 2 skip. **Razem w sandboxie: 123 passed,
  0 failed, 29 skipów** (każdy z przypisanym powodem). Maszyny użytkownika wymagają
  naprawdę tylko `test_migrations.py` + `test_refresh_prices.py` (import sqlalchemy
  na górze) oraz ścieżki API/DB.
- **E2E deterministyczny** (niemodyfikowane funkcje `scripts/validate_thesis.py`
  odtworzone nad cache'em DEC z dysku, bajt-w-bajt z commitowanymi fixturami):
  **23/24** liczb z dokumentu odtwarza się dokładnie — jedyny wyjątek to skorygowany
  wiersz „Dywidenda". Fabrication guard na żywym wyjściu: **32** liczby wejściowe vs
  **9** odczytane, **0** zmyślonych. `evaluate_case`: DGN „0 z 4 wskaźników" i SNT
  „0 z 2" → `insufficient_data`, `matches=True`; źródła SNT prowadzą flagą
  „NIEzweryfikowane".
- **Sanity `classify_size` (realne liczby):** SNT raportowana kap. 3 213 775 722
  (zapis live-20260708) → **mid**; **jedno** grzeczne żywe `web_fetch`
  `https://www.biznesradar.pl/notowania/PKNORLEN` (200, redirect →`/notowania/ORLEN`,
  markdown) → ręcznie odczytana „Kapitalizacja: 159 977 814 352" → **large** (czynnik
  rozmiaru odwraca PRO→CON; na archetypie testowym small=attractive / mid=neutral /
  large=neutral). **Log żądań: 1 żądanie `web_fetch` w całej sesji, 0 retry, brak
  archiwum, brak paginacji, SNT nie pobierane ponownie** — grzeczność respektowana.
- **Fallback bez klucza:** `thesis_ai` zwraca dokładnie `build_thesis().to_dict()`
  + `engine:"deterministic"`, bez `ai_notes`, bez tworzenia katalogu cache.
- **Frontend:** `tsc --noEmit` (strict, cała apka) exit 0 (TypeScript 5.9.3, 28
  plików); `types.ts` ↔ `ThesisOut` pole-w-pole; `ThesisPanel` — stany zdegradowane,
  chipy, disclaimer i kolejność zweryfikowane (dwa niuanse obronne: brak dedykowanej
  gałęzi `insufficient_data` — opiera się na zawsze-niepustym `rationale` z backendu;
  disclaimer `&&`-strzeżony, choć stała backendu jest bezwarunkowa).
