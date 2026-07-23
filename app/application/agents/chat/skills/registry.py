"""Skill registry — procedural memory loaded once at startup.

Each skill is a markdown file in this directory with a small frontmatter block:

    ---
    name: generate-profit-and-loss
    description: one line — used for catalog matching
    when_to_use: trigger phrases / situations
    ---
    <the procedure body>

The registry is built at import time (a module-level singleton, like the chat
graph) so `load_skill` serves bodies from memory with no per-call disk I/O. The
catalog (name + description of every skill) is injected into the system prompt so
the model always knows what it can load; the body enters context only when the
model calls load_skill(name).
"""

from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

_SKILLS_DIR = Path(__file__).parent
_FRONTMATTER_KEYS = ("name", "description", "when_to_use")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    when_to_use: str
    body: str


def _parse(path: Path) -> Skill | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        logger.warning("skill %s has no frontmatter — skipped", path.name)
        return None

    _, front, body = text.split("---", 2)
    meta = {}
    for line in front.strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    name = meta.get("name") or path.stem
    return Skill(
        name=name,
        description=meta.get("description", ""),
        when_to_use=meta.get("when_to_use", ""),
        body=body.strip(),
    )


def _load() -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    for path in sorted(_SKILLS_DIR.glob("*.md")):
        skill = _parse(path)
        if skill is not None:
            skills[skill.name] = skill
    logger.info("skill registry loaded: %d skills (%s)", len(skills), ", ".join(skills))
    return skills


# Built once at import — the in-memory registry.
_REGISTRY: dict[str, Skill] = _load()


def get_skill(name: str) -> Skill | None:
    return _REGISTRY.get(name)


def catalog() -> str:
    """`- name — description` lines for the system prompt."""
    return "\n".join(f"- {s.name} — {s.description}" for s in _REGISTRY.values())


def all_names() -> list[str]:
    return list(_REGISTRY)


def reload() -> None:
    """Dev helper: re-scan the skills directory."""
    global _REGISTRY
    _REGISTRY = _load()
