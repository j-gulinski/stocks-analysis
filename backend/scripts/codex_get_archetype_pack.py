"""Print one canonical company-research archetype pack as JSON.

Usage:
    cd backend
    python3 scripts/codex_get_archetype_pack.py --archetype software-services --pretty
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.codex_common import ScriptError, add_json_flags, run_main, write_json

from app.services.archetype_packs import get_pack, pack_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Return one canonical research archetype pack as JSON."
    )
    parser.add_argument("--archetype", required=True)
    add_json_flags(parser)
    args = parser.parse_args()

    pack = get_pack(args.archetype.strip())
    if pack is None:
        raise ScriptError(f"Unknown archetype '{args.archetype}'.", code=2)
    write_json({"ok": True, "archetype_pack": pack_payload(pack)}, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    run_main(main)
