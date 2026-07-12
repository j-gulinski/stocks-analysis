"""Persist verifier_strict output for one exact frozen portfolio review draft."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError

from app.api.schemas import PortfolioReviewVerificationIn
from app.db.base import SessionLocal
from app.services.portfolio_review_artifacts import (
    PortfolioReviewArtifactError,
    verify_portfolio_review,
)
from scripts.codex_common import (
    ScriptError,
    add_json_flags,
    read_payload,
    run_main,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify one exact portfolio review draft."
    )
    parser.add_argument("--input", default="-")
    add_json_flags(parser)
    args = parser.parse_args()
    try:
        payload = PortfolioReviewVerificationIn.model_validate(read_payload(args.input))
    except ValidationError as exc:
        raise ScriptError(str(exc), code=2) from exc
    with SessionLocal() as db:
        try:
            row = verify_portfolio_review(db, payload)
        except PortfolioReviewArtifactError as exc:
            raise ScriptError(str(exc)) from exc
        write_json(
            {
                "ok": True,
                "verification_run": {
                    "id": row.id,
                    "agent_run_id": row.agent_run_id,
                    "requested_model_role": row.model_role,
                    "requested_model": (row.checks or {}).get("requested_model"),
                    "reasoning_effort": (row.checks or {}).get("reasoning_effort"),
                    "actual_host_model": row.verifier_model,
                    "substitution_or_escalation": (row.checks or {}).get(
                        "substitution_or_escalation"
                    ),
                    "verdict": row.verdict,
                    "checks": row.checks,
                    "summary": row.summary,
                    "created_at": row.created_at,
                },
            },
            pretty=args.pretty,
        )
    return 0


if __name__ == "__main__":
    run_main(main)
