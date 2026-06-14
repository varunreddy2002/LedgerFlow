"""Parser Registry — the central hub where parsers self-register.

OOP concept: Registry Pattern
  - Parsers announce themselves using @ParserRegistry.register decorator
  - The registry holds a list of parser classes
  - resolve() asks each registered parser "can you handle this?" and
    returns the first one that says yes
  - Adding a new bank parser = create file + one decorator + one import
    in __init__.py. Nothing else changes.

This is the OPEN/CLOSED principle in action:
  Open for extension  → add new parsers freely
  Closed for modification → this file never needs to change
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.parsers.base import BaseParser


class ParserRegistry:
    """Central registry for all CSV parsers.

    Parsers join the registry by decorating their class with
    @ParserRegistry.register. The registry stores the class (not an
    instance) so each parse call gets a fresh object.
    """

    # Class-level list: shared across all code, populated at import time
    _parsers: list[type[BaseParser]] = []

    @classmethod
    def register(cls, parser_cls: type[BaseParser]) -> type[BaseParser]:
        """Decorator — adds a parser class to the registry.

        Usage:
            @ParserRegistry.register
            class ChaseParser(BaseParser):
                source_name = "chase"
                ...

        The decorator returns the class unchanged so it can still be used
        normally. The only side effect is appending it to _parsers.
        """
        cls._parsers.append(parser_cls)
        return parser_cls  # return unchanged so the class definition is unaffected

    @classmethod
    def resolve(cls, headers: set[str]) -> BaseParser:
        """Find and return the right parser for the given CSV headers.

        POLYMORPHISM in action: every registered parser has a can_handle()
        method. We call the SAME method on each, but each class does
        something different internally. We don't care which class it is —
        we just ask the question and take the first yes.

        Falls back to GenericParser if no registered parser matches.
        """
        for parser_cls in cls._parsers:
            instance = parser_cls()
            if instance.can_handle(headers):
                return instance

        # Lazy import to avoid circular dependency
        from app.services.parsers.generic import GenericParser
        return GenericParser()

    @classmethod
    def registered_sources(cls) -> list[str]:
        """Return source names of all registered parsers (useful for debugging)."""
        return [p.source_name for p in cls._parsers]
