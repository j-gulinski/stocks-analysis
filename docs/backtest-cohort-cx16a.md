# CX.16 — frozen historical cohort and replay cards

Status: research-only and `needs-human`; this manifest is not a performance
claim. Membership was frozen 2026-07-10 from
`backend/app/services/strategies/cases.py` at revision `fb0794d`, before replay
or tuning. Identity resolution added later does not change membership.

## Membership

| Case | Resolved market identity | Cohort label | Historical anchor | Replay status |
|---|---|---|---|---|
| DGN | Digital Network, `DIG`, ISIN `PL4FNMD00013`, GPW | documented winner | POS flag, month 2023-02; exact day absent | blocked: no exact anchor or point-in-time inputs |
| OPTEX | Optex Systems Holdings, `OPXS`, Nasdaq | control candidate | analysis month 2025-01; exact day absent | blocked and outcome unquantified |
| SUNTECH | Suntech, `SUN`, ISIN `PLSNTCH00012`, NewConnect | documented failure | exact disclosure anchor 2023-03-31 | blocked: no admissible local base-price history |
| SNT | Synektik, `SNT`, GPW | unverified placeholder | no verified entry date | excluded from scored cohort |

The initial frozen mix is therefore one documented hit, one documented miss,
one unmeasured control candidate and one excluded placeholder. No delisted case
was identified in the stored corpus; the delisting cell remains an explicit
gap rather than an assumed survivor.

## Survivorship and availability limits

- This is a hand-authored source corpus, not a declared GPW universe or random
  sample. Selection and denominator are unknown.
- DGN and SUNTECH have qualitative/source anchors but no complete immutable
  report publication timeline, entry fundamentals or corporate-action-aware
  total-return series in the workbench.
- OPTEX is not a GPW case and has no quantified outcome, so it cannot serve as
  a matched control until the exact date and outcome are independently sourced.
- SNT remains excluded because its attribution and historical anchor are not
  verified. No current price or later restatement may fill these gaps.
- No replay, strategy-weight change or performance summary is allowed from this
  manifest. CX.16b must reconstruct available inputs with an explicit lag
  policy, after which `verifier_strict` must audit look-ahead boundaries.

## 1/2/3-year cards (CX.16d)

`backend/scripts/codex_review_frozen_cohort.py` now emits deterministic cards
for 365/730/1095 days. The current real run has no numeric return for any case:

| Case | 1 year | 2 years | 3 years | Strict reason |
|---|---:|---:|---:|---|
| DGN / DIG | unavailable | unavailable | unavailable | exact anchor day absent |
| OPTEX / OPXS | unavailable | unavailable | unavailable | exact anchor day and quantified outcome absent |
| SUNTECH / SUN | unavailable | unavailable | unavailable | no local price row known at the 2023-03-31 anchor |
| SNT | excluded | excluded | excluded | attribution and anchor unverified |

The engine requires an exact anchor plus a base `Price` whose `scraped_at` is
on or before that price date. Later prices are outcome-only. Identity resolution
therefore cannot unlock a return by itself. The verified runtime check is strict
SNT replay run 4: zero observations with `needs-human`; the earlier run 3 was
reclassified from the old `pending` state after the contract fix. Neither is a
cohort result.

Identity sources: [GPW issuer list for DIG](https://biznes.pap.pl/download/attachment/51210629/DOC.20250327.51210629.Uch_441.pdf),
[Digital Network issuer reports](https://digitalnetwork.pl/raporty/raporty-okresowe/),
[Suntech Q3 2023 issuer report](https://www.suntech.pl/images/files/reports/2023/EBI/11b.pdf),
[SEC filing for OPXS](https://www.sec.gov/Archives/edgar/data/1397016/000149315226022360/form8-k.htm).

## Strict verifier result

Verdict: `needs-human`. Source-grounded identity and the no-look-ahead boundary
pass. Complete numeric outcomes fail: DGN/OPXS lack exact dates, SUN lacks an
admissible local base price, and SNT remains excluded. There are no accepted
false-positive/false-negative classifications and no supported aggregate
performance claim. Required fixes are exact anchors, original filing
availability and corporate-action-aware total-return prices.

Next slice: freeze exact DGN/OPXS anchors and corporate-action-aware historical
prices, then reconstruct publication availability and original filing versions.
Missing values stay `unknown`; no aggregate performance is allowed before that.
