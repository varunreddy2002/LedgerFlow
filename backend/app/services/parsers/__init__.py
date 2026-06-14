"""Parser package — importing this module auto-registers all parsers.

HOW THE REGISTRY WORKS:
  When Python imports a module, it runs the top-level code in that file.
  @ParserRegistry.register is a decorator that runs at import time.
  So importing `chase` and `stripe` here causes their @register decorators
  to fire, adding them to ParserRegistry._parsers automatically.

HOW TO ADD A NEW BANK PARSER:
  1. Create  app/services/parsers/mercury.py
  2. Implement BaseParser + decorate with @ParserRegistry.register
  3. Add the import below — that's it. Nothing else changes.
"""

from app.services.parsers import chase, stripe  # noqa: F401
