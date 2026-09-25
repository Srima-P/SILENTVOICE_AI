"""
OnboardingService — Phase 5 developer onboarding workflow.

Uses existing Phase 2 project analysis to help a new developer understand the project.

Responsibilities:
  • Generate a comprehensive onboarding overview (what the project is, stack, structure)
  • Explain the apparent architecture
  • Generate setup guidance by reading setup files (package.json, README.md, etc.)
  • Suggest beginner tasks based on actual project files and components

All output is grounded in real project data — the service never invents files,
technologies, or architecture patterns that aren't supported by evidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.groq_service import GroqService, GroqError
from app.services.project_scanner import ProjectScanner
from app.services.intent_classifier import Intent

logger = logging.getLogger("silentvoice.onboarding")

# Setup-related file names (read in order, first found wins for primary context)
_SETUP_FILES = [
    "README.md", "README.rst", "README.txt",
    "package.json", "requirements.txt", "pyproject.toml", "setup.py",
    "Makefile", "docker-compose.yml", "docker-compose.yaml",
    ".env.example", "CONTRIBUTING.md",
]


@dataclass
class OnboardingResult:
    """Structured result returned to the explanation service."""
    intent: str
    response: str
    groq_used: bool = True
    error: bool = False
    follow_up_suggestions: list[str] = field(default_factory=list)


class OnboardingService:
    """
    Generates onboarding content for new developers.
    One instance per request (stateless after __init__).
    """

    def __init__(self) -> None:
        self._root = Path(settings.project_root_path)
        self._scanner = ProjectScanner(self._root)
        self._groq = GroqService()

    # ── Public dispatcher ──────────────────────────────────────────────────────

    async def handle(
        self,
        intent: Intent,
        project_analysis,    # ProjectAnalysisResponse | None
    ) -> OnboardingResult:
        """
        Dispatch to the appropriate onboarding handler.
        Never raises — errors are returned as OnboardingResult(error=True).
        """
        try:
            if intent == Intent.ONBOARDING_START:
                return await self._onboarding_start(project_analysis)
            if intent == Intent.ARCHITECTURE_OVERVIEW:
                return await self._architecture_overview(project_analysis)
            if intent == Intent.SETUP_GUIDANCE:
                return await self._setup_guidance(project_analysis)
            if intent == Intent.BEGINNER_TASKS:
                return await self._beginner_tasks(project_analysis)

            return OnboardingResult(
                intent=intent.value,
                response="Unknown onboarding intent.",
                error=True,
            )

        except GroqError as exc:
            logger.warning("Groq error in onboarding: %s", exc)
            return OnboardingResult(
                intent=intent.value,
                response=f"⚠️ **AI Error:** {exc}",
                error=True,
            )
        except Exception as exc:
            logger.exception("Unexpected error in OnboardingService.handle")
            return OnboardingResult(
                intent=intent.value,
                response="An unexpected error occurred during onboarding. Please try again.",
                error=True,
            )

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _onboarding_start(self, project_analysis) -> OnboardingResult:
        """Full onboarding overview for a new developer."""
        ctx = _build_project_context(project_analysis)
        text = await self._groq.onboarding_start(
            project_name=ctx["project_name"],
            total_files=ctx["total_files"],
            languages=ctx["languages"],
            components=ctx["components"],
            dep_sample=ctx["dep_sample"],
            setup_hint=ctx["setup_hint"],
        )
        return OnboardingResult(
            intent=Intent.ONBOARDING_START.value,
            response=text,
            follow_up_suggestions=[
                "Explain the architecture",
                "How do I set up this project?",
                "Give me beginner tasks",
                "Give me a project overview",
            ],
        )

    async def _architecture_overview(self, project_analysis) -> OnboardingResult:
        """Explain the apparent project architecture."""
        ctx = _build_project_context(project_analysis)
        text = await self._groq.architecture_overview(
            project_name=ctx["project_name"],
            languages=ctx["languages"],
            components=ctx["components"],
            dep_sample=ctx["dep_sample"],
            total_files=ctx["total_files"],
        )
        return OnboardingResult(
            intent=Intent.ARCHITECTURE_OVERVIEW.value,
            response=text,
            follow_up_suggestions=[
                "How do I set up this project?",
                "Give me beginner tasks",
                "Give me a project overview",
                "I'm new to this project",
            ],
        )

    async def _setup_guidance(self, project_analysis) -> OnboardingResult:
        """Generate setup guidance by reading setup files where available."""
        setup_contents: dict[str, str] = {}
        for fname in _SETUP_FILES:
            fpath = self._root / fname
            if fpath.exists():
                try:
                    # Pass fname (relative to project root) — safe_read() expects
                    # a path relative to the project root, not an absolute path.
                    # str(fpath) would produce an absolute path that bypasses the
                    # relative-path contract and fails on Windows.
                    content, _ = self._scanner.safe_read(fname)
                    if content.strip():
                        setup_contents[fname] = content[:4000]  # cap per file
                        if len(setup_contents) >= 4:          # limit total files read
                            break
                except Exception:
                    pass

        ctx = _build_project_context(project_analysis)
        text = await self._groq.setup_guidance(
            project_name=ctx["project_name"],
            languages=ctx["languages"],
            setup_contents=setup_contents,
        )
        return OnboardingResult(
            intent=Intent.SETUP_GUIDANCE.value,
            response=text,
            follow_up_suggestions=[
                "I'm new to this project",
                "Explain the architecture",
                "Give me beginner tasks",
                "Give me a project overview",
            ],
        )

    async def _beginner_tasks(self, project_analysis) -> OnboardingResult:
        """Suggest beginner tasks grounded in actual project files."""
        ctx = _build_project_context(project_analysis)
        text = await self._groq.beginner_tasks(
            project_name=ctx["project_name"],
            languages=ctx["languages"],
            components=ctx["components"],
            dep_sample=ctx["dep_sample"],
        )
        return OnboardingResult(
            intent=Intent.BEGINNER_TASKS.value,
            response=text,
            follow_up_suggestions=[
                "Explain the architecture",
                "How do I set up this project?",
                "I'm new to this project",
                "Give me a project overview",
            ],
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_project_context(project_analysis) -> dict:
    """
    Extract a compact, prompt-safe context dictionary from project_analysis.
    Safe to call when project_analysis is None (returns minimal context).
    """
    if project_analysis is None:
        return {
            "project_name": "this project",
            "total_files": 0,
            "languages": {},
            "components": [],
            "dep_sample": {},
            "setup_hint": "",
        }

    comp_list = [c.name for c in project_analysis.components[:20]]
    # Sample up to 10 dependency relationships for the prompt
    dep_sample = dict(list(project_analysis.dependencies.entries.items())[:10])

    return {
        "project_name": project_analysis.project_name,
        "total_files": project_analysis.total_files,
        "languages": project_analysis.languages,
        "components": comp_list,
        "dep_sample": dep_sample,
        "setup_hint": _guess_setup_hint(project_analysis.languages),
    }


def _guess_setup_hint(languages: dict[str, int]) -> str:
    """Return a one-line setup technology hint from language breakdown."""
    if "javascript" in languages or "typescript" in languages:
        return "Node.js/npm project"
    if "python" in languages:
        return "Python project"
    if "java" in languages or "kotlin" in languages:
        return "JVM project"
    if "go" in languages:
        return "Go project"
    if "rust" in languages:
        return "Rust project"
    return ""
