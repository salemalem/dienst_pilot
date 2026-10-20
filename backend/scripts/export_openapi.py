"""Write the API's OpenAPI schema to a file (used to generate packages/api-client)."""

import json
import sys
from pathlib import Path

from dienstpilot.main import app


def main() -> None:
    """Write app.openapi() as pretty JSON to the path given as the first argument."""
    out = Path(sys.argv[1])
    out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
