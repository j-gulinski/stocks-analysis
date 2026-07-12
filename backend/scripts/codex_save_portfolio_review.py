"""Save one immutable portfolio review through its exact verifier gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError

from app.api.schemas import PortfolioReviewSaveIn, PortfolioReviewSnapshotOut
from app.db.base import SessionLocal
from app.services.portfolio_review_artifacts import (
    PortfolioReviewArtifactError,
    save_portfolio_review,
)
from scripts.codex_common import (
    ScriptError,
    add_json_flags,
    read_payload,
    run_main,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Save one immutable portfolio review.")
    parser.add_argument("--input", default="-")
    add_json_flags(parser)
    args = parser.parse_args()
    try:
        payload = PortfolioReviewSaveIn.model_validate(read_payload(args.input))
    except ValidationError as exc:
        raise ScriptError(str(exc), code=2) from exc
    with SessionLocal() as db:
        try:
            row = save_portfolio_review(db, payload)
        except PortfolioReviewArtifactError as exc:
            raise ScriptError(str(exc)) from exc
        write_json(
            {
                "ok": True,
                "portfolio_review_snapshot": PortfolioReviewSnapshotOut.model_validate(
                    row
                ).model_dump(mode="json"),
            },
            pretty=args.pretty,
        )
    return 0


if __name__ == "__main__":
    run_main(main)
