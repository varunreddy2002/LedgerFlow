"""CSV parsing entry point — delegates to the parser registry.

This file is intentionally thin. All parsing logic lives in the
individual parser classes under app/services/parsers/.

To add a new bank format:
  1. Create  app/services/parsers/<bank>.py
  2. Implement BaseParser + @ParserRegistry.register
  3. Add the import in app/services/parsers/__init__.py
  No changes needed here.

Re-exports ParseResult and RowError so callers (routes, tests) don't
need to know where they came from.
"""

import csv
import io

# Importing parsers triggers their @ParserRegistry.register decorators
import app.services.parsers  # noqa: F401

from app.services.parsers.base import ParseResult, RowError  # re-export
from app.services.parsers.registry import ParserRegistry


def parse_csv(
    file_content: bytes,
    business_id: int,
    document_id: int,
    existing_fingerprints: set[str] | None = None,
    account_map: dict[str, int] | None = None,
) -> ParseResult:
    """Parse raw CSV bytes into a list of unsaved Transaction ORM objects.

    Steps:
      1. Decode + read headers
      2. Ask ParserRegistry for the right parser (Chase / Stripe / Generic)
      3. Delegate to that parser's parse() method
      4. Return ParseResult — caller is responsible for DB commit
    """
    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        result = ParseResult()
        result.errors.append(RowError(0, "File is empty or has no header row"))
        return result

    headers = {h.strip().lower() for h in reader.fieldnames if h}

    parser = ParserRegistry.resolve(headers)

    return parser.parse(
        file_content,
        business_id,
        document_id,
        existing_fingerprints,
        account_map,
    )
