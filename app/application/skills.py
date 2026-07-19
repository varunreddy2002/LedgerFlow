"""On-demand skill playbooks (the token-saver).

A *skill* is a markdown file with simple frontmatter (`name`, `description`,
`when_to_use`, `tools`) and a playbook body. Only a one-line **index** of skills sits
in the system prompt; the full playbook is fetched on demand via ``load_skill(name)``.
This is the deferred-loading pattern that replaces the old always-on 100-line schema.

Frontmatter is parsed without a YAML dependency (the format is deliberately tiny), so
this module has no third-party imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from app.core.logging import get_logger
from app.application.accounting.errors import SkillNotFoundError

logger = get_logger(__name__)

# Repo-root/skills — three parents up from app/application/skills.py.
DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


@dataclass(frozen=True)
class Skill:
    """A parsed skill playbook."""

    name: str
    description: str
    when_to_use: str
    tools: List[str]
    body: str

    def index_line(self) -> str:
        """One-line index entry for the system prompt."""
        return f"- {self.name}: {self.description} (use for: {self.when_to_use})"

    def render(self) -> str:
        """The full playbook text returned by ``load_skill``."""
        tools = ", ".join(self.tools) if self.tools else "(none)"
        return f"# Skill: {self.name}\nTools: {tools}\n\n{self.body.strip()}\n"


class SkillRegistry:
    """Loads and serves skills from a directory. Immutable after construction."""

    def __init__(self, skills_dir: Path = DEFAULT_SKILLS_DIR) -> None:
        self._skills: Dict[str, Skill] = {}
        self._dir = skills_dir
        self._load()

    def _load(self) -> None:
        if not self._dir.is_dir():
            logger.warning("[skills] directory %s not found; no skills loaded", self._dir)
            return
        for path in sorted(self._dir.glob("*.md")):
            try:
                skill = self._parse(path)
            except Exception as exc:  # a malformed skill must not break startup
                logger.warning("[skills] failed to parse %s: %s", path.name, exc)
                continue
            self._skills[skill.name] = skill
        logger.info("[skills] loaded %d skill(s): %s",
                    len(self._skills), ", ".join(sorted(self._skills)))

    @staticmethod
    def _parse(path: Path) -> Skill:
        text = path.read_text(encoding="utf-8")
        meta: Dict[str, str] = {}
        body = text
        if text.startswith("---"):
            _, frontmatter, body = text.split("---", 2)
            for line in frontmatter.strip().splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()

        tools_raw = meta.get("tools", "").strip().strip("[]")
        tools = [t.strip() for t in tools_raw.split(",") if t.strip()]
        return Skill(
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            when_to_use=meta.get("when_to_use", ""),
            tools=tools,
            body=body,
        )

    # ── public API ────────────────────────────────────────────────────────────
    def index(self) -> str:
        """The lightweight skill index for the system prompt (one line per skill)."""
        if not self._skills:
            return "(no skills available)"
        return "\n".join(s.index_line() for s in self._skills.values())

    def names(self) -> List[str]:
        return list(self._skills)

    def load(self, name: str) -> Skill:
        """Return a skill by name, or raise :class:`SkillNotFoundError`."""
        skill = self._skills.get(name)
        if skill is None:
            raise SkillNotFoundError(name)
        logger.info("[skills] loaded skill %r on demand", name)
        return skill


# A process-wide registry (skills are static, repo-versioned files).
skill_registry = SkillRegistry()
