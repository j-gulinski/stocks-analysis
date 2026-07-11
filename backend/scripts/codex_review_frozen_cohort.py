"""Print honest 1/2/3-year availability cards for the frozen CX.16 cohort."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.base import SessionLocal
from app.services.cohort_replay import build_frozen_cohort_review
from scripts.codex_common import add_json_flags, run_main, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Review the frozen CX.16 cohort.")
    add_json_flags(parser)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        result = build_frozen_cohort_review(db)
    finally:
        db.close()
    write_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    run_main(main)
