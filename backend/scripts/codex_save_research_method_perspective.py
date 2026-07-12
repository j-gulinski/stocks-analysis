"""Save one immutable snapshot-bound Research method perspective."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError

from app.api.schemas import ResearchMethodPerspectiveOut, ResearchMethodPerspectiveSaveIn
from app.db.base import SessionLocal
from app.services.research_method_perspectives import (
    ResearchMethodPerspectiveError,
    save_research_method_perspective,
)
from scripts.codex_common import ScriptError, add_json_flags, read_payload, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Save an immutable Research method perspective.")
    parser.add_argument("--case-id", type=int, required=True)
    parser.add_argument("--input", default="-", help="Perspective JSON file, or '-' for stdin.")
    add_json_flags(parser)
    args = parser.parse_args()
    try:
        payload = ResearchMethodPerspectiveSaveIn.model_validate(read_payload(args.input))
    except ValidationError as exc:
        raise ScriptError(str(exc), code=2) from exc
    db = SessionLocal()
    try:
        try:
            perspective = save_research_method_perspective(
                db, case_id=args.case_id, payload=payload
            )
        except ResearchMethodPerspectiveError as exc:
            raise ScriptError(str(exc), code=1) from exc
        write_json(
            {
                "ok": True,
                "research_method_perspective": ResearchMethodPerspectiveOut.model_validate(
                    perspective
                ).model_dump(mode="json"),
            },
            pretty=args.pretty,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    run_main(main)
