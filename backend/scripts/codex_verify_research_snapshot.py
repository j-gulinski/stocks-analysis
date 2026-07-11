"""Record verifier_strict output for one exact research snapshot draft."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError

from app.api.schemas import ResearchSnapshotVerificationIn
from app.db.base import SessionLocal
from app.services.research_artifacts import ResearchArtifactError, verify_research_snapshot
from scripts.codex_common import ScriptError, add_json_flags, read_payload, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Persist an independent verdict for an exact research draft."
    )
    parser.add_argument("--case-id", type=int, required=True)
    parser.add_argument("--input", default="-", help="Verification JSON file, or '-' for stdin.")
    add_json_flags(parser)
    args = parser.parse_args()
    try:
        payload = ResearchSnapshotVerificationIn.model_validate(read_payload(args.input))
    except ValidationError as exc:
        raise ScriptError(str(exc), code=2) from exc

    db = SessionLocal()
    try:
        try:
            verification = verify_research_snapshot(db, case_id=args.case_id, payload=payload)
        except ResearchArtifactError as exc:
            raise ScriptError(str(exc), code=1) from exc
        write_json(
            {
                "ok": True,
                "verification_run": {
                    "id": verification.id,
                    "agent_run_id": verification.agent_run_id,
                    "model_role": verification.model_role,
                    "verifier_model": verification.verifier_model,
                    "verdict": verification.verdict,
                    "checks": verification.checks,
                    "summary": verification.summary,
                    "created_at": verification.created_at,
                },
            },
            pretty=args.pretty,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    run_main(main)
