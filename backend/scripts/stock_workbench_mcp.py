"""Run the Stock Analysis Workbench MCP stdio server."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.mcp.stock_workbench_server import serve_stdio


if __name__ == "__main__":
    raise SystemExit(serve_stdio())
