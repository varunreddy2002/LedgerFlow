"""Central logging setup.

One configuration point for the whole app. Modules call `get_logger(__name__)`
to obtain a logger; configuration happens once (idempotent) on first use.
"""

import logging
import sys

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a stdout handler to the root logger exactly once."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger, ensuring logging is configured first."""
    configure_logging()
    return logging.getLogger(name)
