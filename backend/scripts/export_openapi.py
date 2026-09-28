"""Export the API's OpenAPI schema for the typed frontend client.

The frontend generates its TypeScript types from ``frontend/openapi.json``
(``npm run gen:api``), so that file must match what the backend actually
serves. ``tests/test_openapi_contract.py`` fails when it drifts.

Usage:
  cd backend
  python -m scripts.export_openapi          # rewrite frontend/openapi.json
  python -m scripts.export_openapi --check  # exit 1 if it is out of date
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def render(schema: dict[str, Any]) -> str:
    """Stable formatting, so the file only changes when the API does."""
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def build_schema() -> dict[str, Any]:
    # Building the schema never connects to anything, but Settings requires the
    # URLs to be present. These placeholders hold no credentials.
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://openapi@localhost/openapi")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    from app.main import create_app

    return create_app().openapi()


def main() -> int:
    rendered = render(build_schema())
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(
                f"{OUTPUT} is out of date; run: python -m scripts.export_openapi", file=sys.stderr
            )
            return 1
        print(f"{OUTPUT} is up to date")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
