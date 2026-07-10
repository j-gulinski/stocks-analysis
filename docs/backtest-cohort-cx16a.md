# CX.16a — frozen historical cohort

Status: research-only and `needs-human`; this manifest is not a performance
claim. Frozen 2026-07-10 from `backend/app/services/strategies/cases.py` at
revision `fb0794d`, before any replay or tuning.

## Membership

| Case | Cohort label | Historical anchor | What is actually known | Replay status |
|---|---|---|---|---|
| DGN | documented winner | POS flag, 2023-02 | Malik source documents a repricing of about +2500% over five years; entry price and entry-era fundamentals are not reconstructed | blocked pending point-in-time inputs |
| OPTEX | control candidate | first foreign investment, 2025-01 | Entry pattern is documented (trailing P/E about 12, forecast below 10, rising backlog); exact ticker/ISIN and outcome are missing | not a verified control |
| SUNTECH | documented failure | IKE portfolio, 2021–2024 | Average entry price about 2.40 PLN and a qualitative thesis miss are documented; exact GPW identity and entry multiple are missing | blocked pending identity/price history |
| SNT | unverified placeholder | no verified entry date | Early-catch attribution is explicitly unverified; the repository fixture is not an investment record | exclude from scored cohort |

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
  a matched control until identity, date and outcome are independently sourced.
- SNT remains excluded because its attribution and historical anchor are not
  verified. No current price or later restatement may fill these gaps.
- No replay, strategy-weight change or performance summary is allowed from this
  manifest. CX.16b must reconstruct available inputs with an explicit lag
  policy, after which `verifier_strict` must audit look-ahead boundaries.

Next slice: reconstruct each eligible case's historical identity, publication
availability and price coverage; keep missing fields as `unknown`.
