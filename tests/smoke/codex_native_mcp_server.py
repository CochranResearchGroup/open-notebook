from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP


def create_server(log_path: Path, marker: str) -> FastMCP:
    server = FastMCP(
        "Open Notebook Native MCP Smoke",
        instructions="Return the hidden Open Notebook native MCP smoke marker.",
    )

    @server.tool
    def native_smoke_lookup(request: str = "") -> str:
        """Return the hidden Open Notebook native MCP smoke marker."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "called_at": datetime.now(UTC).isoformat(),
                        "tool": "native_smoke_lookup",
                        "request": request,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        return marker

    return server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Env-free MCP server used by Codex App Server smoke tests."
    )
    parser.add_argument("--log-path", required=True)
    marker_group = parser.add_mutually_exclusive_group(required=True)
    marker_group.add_argument("--marker")
    marker_group.add_argument("--marker-env")
    args = parser.parse_args()

    marker = args.marker if args.marker is not None else os.environ[args.marker_env]
    create_server(Path(args.log_path), marker).run(transport="stdio")


if __name__ == "__main__":
    main()
