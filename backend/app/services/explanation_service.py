"""
ExplanationService — orchestrates file reading, context gathering, and Groq calls.

This is the central Phase 3 service.  It:
  1. Receives a classified intent + optional resolved file path
  2. Reads the file safely via ProjectScanner
  3. Gathers dependency metadata from Phase 2 analysis
  4. Enforces the AI file-size limit
  5. Delegates to GroqService for text generation
  6. Returns a structured response
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.groq_service import GroqService, GroqError
from app.services.intent_classifier import Intent
from app.services.project_scanner import ProjectScanner
from app.services.dependency_analyzer import DependencyAnalyzer

logger = logging.getLogger("silentvoice.explanation")


@dataclass
class ExplanationResult:
    """Structured result returned to the API route."""
    intent: str
    target_file: Optional[str]
    response: str
    groq_used: bool = True
    error: bool = False


class ExplanationService:
    """
    Orchestrates all Phase 3 AI explanation workflows.

    One instance per request is fine (stateless after __init__).
    """

    def __init__(self) -> None:
        self._root = Path(settings.project_root_path)
        self._scanner = ProjectScanner(self._root)
        self._analyzer = DependencyAnalyzer(self._root)
        self._groq = GroqService()

    # ── Public dispatch method ─────────────────────────────────────────────────

    async def handle(
        self,
        intent: Intent,
        resolved_file: Optional[str],
        project_analysis,          # ProjectAnalysisResponse | None
    ) -> ExplanationResult:
        """
        Dispatch to the appropriate handler based on *intent*.
        Never raises — all errors are returned as ExplanationResult(error=True).
        """
        try:
            if intent == Intent.PROJECT_OVERVIEW:
                return await self._project_overview(project_analysis)

            if intent in (Intent.EXPLAIN_FILE, Intent.SUMMARIZE_FILE, Intent.EXPLAIN_DEPENDENCIES):
                if not resolved_file:
                    return ExplanationResult(
                        intent=intent.value,
                        target_file=None,
                        response="I need a file name to work with. Try: **Explain Login.jsx**",
                        error=True,
                    )
                return await self._file_intent(intent, resolved_file, project_analysis)

            # Unsupported
            return ExplanationResult(
                intent=intent.value,
                target_file=resolved_file,
                response=(
                    "I didn't understand that request.\n\n"
                    "**Try one of these:**\n"
                    "- `Explain Login.jsx`\n"
                    "- `Summarize App.jsx`\n"
                    "- `Explain dependencies of App.jsx`\n"
                    "- `Give me a project overview`"
                ),
                groq_used=False,
                error=True,
            )

        except GroqError as exc:
            logger.warning("Groq error: %s", exc)
            return ExplanationResult(
                intent=intent.value,
                target_file=resolved_file,
                response=f"⚠️ **AI Error:** {exc}",
                error=True,
            )
        except Exception as exc:
            logger.exception("Unexpected error in ExplanationService.handle")
            return ExplanationResult(
                intent=intent.value,
                target_file=resolved_file,
                response="An unexpected error occurred. Please try again.",
                error=True,
            )

    # ── File-level intents ─────────────────────────────────────────────────────

    async def _file_intent(
        self,
        intent: Intent,
        file_path: str,
        project_analysis,
    ) -> ExplanationResult:
        """Read the file, build context, call Groq."""
        # 1. Read the file (safe — path already validated by route)
        try:
            content, _ = self._scanner.safe_read(file_path)
        except (FileNotFoundError, ValueError, PermissionError) as exc:
            return ExplanationResult(
                intent=intent.value,
                target_file=file_path,
                response=f"Could not read `{file_path}`: {exc}",
                error=True,
            )

        # 2. Enforce AI size limit
        byte_size = len(content.encode("utf-8"))
        if byte_size > settings.max_file_size_for_ai:
            kb = byte_size // 1024
            limit_kb = settings.max_file_size_for_ai // 1024
            return ExplanationResult(
                intent=intent.value,
                target_file=file_path,
                response=(
                    f"**`{file_path}` is too large to analyze directly** ({kb} KB).\n\n"
                    f"The current AI limit is {limit_kb} KB. "
                    "Consider asking about a specific section of the file."
                ),
                groq_used=False,
                error=True,
            )

        # 3. Detect language
        lang = _detect_language(file_path)

        # 4. Gather dependency info from Phase 2 analysis
        resolved_deps: list[str] = []
        unresolved_deps: list[str] = []
        if project_analysis:
            resolved_deps = project_analysis.dependencies.entries.get(file_path, [])
            unresolved_deps = project_analysis.dependencies.unresolved.get(file_path, [])

        # 5. Dispatch to appropriate Groq prompt
        if intent == Intent.EXPLAIN_FILE:
            text = await self._groq.explain_file(
                file_path=file_path,
                language=lang,
                content=content,
                dependencies=resolved_deps,
            )
        elif intent == Intent.SUMMARIZE_FILE:
            text = await self._groq.summarize_file(
                file_path=file_path,
                language=lang,
                content=content,
            )
        else:  # EXPLAIN_DEPENDENCIES
            text = await self._groq.explain_dependencies(
                file_path=file_path,
                resolved_deps=resolved_deps,
                unresolved_deps=unresolved_deps,
                file_content=content,
                language=lang,
            )

        return ExplanationResult(
            intent=intent.value,
            target_file=file_path,
            response=text,
        )

    # ── Project overview ───────────────────────────────────────────────────────

    async def _project_overview(self, project_analysis) -> ExplanationResult:
        """Generate a project-level overview from Phase 2 metadata."""
        if not project_analysis:
            # No cached analysis — run a quick scan to get metadata
            try:
                tree = self._scanner.scan()
            except Exception as exc:
                return ExplanationResult(
                    intent=Intent.PROJECT_OVERVIEW.value,
                    target_file=None,
                    response=f"Could not scan project: {exc}",
                    error=True,
                )
            # Minimal metadata without full file reads
            text = await self._groq.project_overview(
                project_name=tree.name,
                total_files=tree.total_files,
                source_files=tree.total_files,
                languages={},
                components=[],
                dependency_entries={},
            )
        else:
            comp_names = [c.name for c in project_analysis.components]
            text = await self._groq.project_overview(
                project_name=project_analysis.project_name,
                total_files=project_analysis.total_files,
                source_files=project_analysis.source_files,
                languages=project_analysis.languages,
                components=comp_names,
                dependency_entries=project_analysis.dependencies.entries,
            )

        return ExplanationResult(
            intent=Intent.PROJECT_OVERVIEW.value,
            target_file=None,
            response=text,
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

_LANG_MAP: dict[str, str] = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".html": "html",
    ".css": "css", ".scss": "css", ".json": "json", ".md": "markdown",
    ".yaml": "yaml", ".yml": "yaml", ".sh": "shell", ".go": "go",
    ".rs": "rust", ".java": "java", ".kt": "kotlin", ".rb": "ruby",
    ".php": "php", ".c": "c", ".cpp": "cpp", ".cs": "csharp",
    ".vue": "vue", ".svelte": "svelte",
}

def _detect_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return _LANG_MAP.get(ext, "text")
