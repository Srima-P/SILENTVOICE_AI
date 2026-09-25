"""
ExplanationService — orchestrates file reading, context gathering, and Groq calls.

Phase 3 core + Phase 4 extensions:
  Phase 3:
    1. Receives a classified intent + optional resolved file path
    2. Reads the file safely via ProjectScanner
    3. Gathers dependency metadata from Phase 2 analysis
    4. Enforces the AI file-size limit
    5. Delegates to GroqService for text generation
  Phase 4 additions:
    6. Handles FIND_DEPENDENTS, EXPLAIN_RELATIONSHIP, SHOW_RELATED intents
    7. Generates contextual follow-up suggestions for every response
    8. Accepts second_file for relationship queries
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.groq_service import GroqService, GroqError
from app.services.intent_classifier import Intent
from app.services.project_scanner import ProjectScanner
from app.services.dependency_analyzer import DependencyAnalyzer
from app.services.onboarding_service import OnboardingService, OnboardingResult

logger = logging.getLogger("silentvoice.explanation")


@dataclass
class ExplanationResult:
    """Structured result returned to the API route."""
    intent: str
    target_file: Optional[str]
    response: str
    groq_used: bool = True
    error: bool = False
    follow_up_suggestions: list[str] = field(default_factory=list)


class ExplanationService:
    """
    Orchestrates all AI explanation workflows (Phase 3 + Phase 4).

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
        project_analysis,           # ProjectAnalysisResponse | None
        second_file: Optional[str] = None,   # Phase 4: for relationship queries
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

            # ── Phase 4 intents ────────────────────────────────────────────────
            if intent == Intent.FIND_DEPENDENTS:
                if not resolved_file:
                    return ExplanationResult(
                        intent=intent.value,
                        target_file=None,
                        response=(
                            "I need a file name to look up dependents for. "
                            "Try: **Which files depend on Login.jsx?**"
                        ),
                        error=True,
                    )
                return await self._find_dependents(resolved_file, project_analysis)

            if intent == Intent.EXPLAIN_RELATIONSHIP:
                if not resolved_file:
                    return ExplanationResult(
                        intent=intent.value,
                        target_file=None,
                        response=(
                            "I need at least one file name to analyse a relationship. "
                            "Try: **How does Login.jsx connect to App.jsx?**"
                        ),
                        error=True,
                    )
                return await self._explain_relationship(resolved_file, second_file, project_analysis)

            if intent == Intent.SHOW_RELATED:
                if not resolved_file:
                    return ExplanationResult(
                        intent=intent.value,
                        target_file=None,
                        response=(
                            "I need a file name to show related files for. "
                            "Try: **Show related components for Login.jsx**"
                        ),
                        error=True,
                    )
                return await self._show_related(resolved_file, project_analysis)

            # ── Phase 5 intents — delegate to OnboardingService ────────────────
            _ONBOARDING_INTENTS = (
                Intent.ONBOARDING_START,
                Intent.ARCHITECTURE_OVERVIEW,
                Intent.SETUP_GUIDANCE,
                Intent.BEGINNER_TASKS,
            )
            if intent in _ONBOARDING_INTENTS:
                ob_svc = OnboardingService()
                ob_result = await ob_svc.handle(intent, project_analysis)
                return ExplanationResult(
                    intent=ob_result.intent,
                    target_file=None,
                    response=ob_result.response,
                    groq_used=ob_result.groq_used,
                    error=ob_result.error,
                    follow_up_suggestions=ob_result.follow_up_suggestions,
                )

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
                    "- `Give me a project overview`\n"
                    "- `Which files depend on Login.jsx?`\n"
                    "- `Show related components`\n"
                    "- `I'm new to this project`\n"
                    "- `How do I set up this project?`"
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

    # ── Phase 3: File-level intents ────────────────────────────────────────────

    async def _file_intent(
        self,
        intent: Intent,
        file_path: str,
        project_analysis,
    ) -> ExplanationResult:
        """Read the file, build context, call Groq."""
        try:
            content, _ = self._scanner.safe_read(file_path)
        except (FileNotFoundError, ValueError, PermissionError) as exc:
            return ExplanationResult(
                intent=intent.value,
                target_file=file_path,
                response=f"Could not read `{file_path}`: {exc}",
                error=True,
            )

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

        lang = _detect_language(file_path)
        resolved_deps: list[str] = []
        unresolved_deps: list[str] = []
        if project_analysis:
            resolved_deps = project_analysis.dependencies.entries.get(file_path, [])
            unresolved_deps = project_analysis.dependencies.unresolved.get(file_path, [])

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

        suggestions = _generate_follow_up_suggestions(intent, file_path, project_analysis)
        return ExplanationResult(
            intent=intent.value,
            target_file=file_path,
            response=text,
            follow_up_suggestions=suggestions,
        )

    # ── Phase 3: Project overview ──────────────────────────────────────────────

    async def _project_overview(self, project_analysis) -> ExplanationResult:
        """Generate a project-level overview from Phase 2 metadata."""
        if not project_analysis:
            try:
                tree = self._scanner.scan()
            except Exception as exc:
                return ExplanationResult(
                    intent=Intent.PROJECT_OVERVIEW.value,
                    target_file=None,
                    response=f"Could not scan project: {exc}",
                    error=True,
                )
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

        suggestions = [
            "Explain the main entry point",
            "Which files have the most dependencies?",
            "Show related components",
            "Explain the project structure",
        ]
        return ExplanationResult(
            intent=Intent.PROJECT_OVERVIEW.value,
            target_file=None,
            response=text,
            follow_up_suggestions=suggestions,
        )

    # ── Phase 4: Find dependents ───────────────────────────────────────────────

    async def _find_dependents(
        self,
        file_path: str,
        project_analysis,
    ) -> ExplanationResult:
        """Compute reverse dependencies and ask Groq to explain them."""
        dependents: list[str] = []
        if project_analysis:
            dependents = _reverse_deps(file_path, project_analysis.dependencies.entries)

        lang = _detect_language(file_path)

        if not dependents:
            # Return a useful no-Groq response if nothing depends on this file
            text = (
                f"## Files That Depend On `{file_path}`\n\n"
                f"No files in the project were found to import or depend on `{file_path}`.\n\n"
                "This could mean:\n"
                "- It is an entry point (e.g., `main.jsx`, `index.ts`)\n"
                "- It is a standalone module not yet used elsewhere\n"
                "- Dependency analysis has not been run yet"
            )
            suggestions = _generate_follow_up_suggestions(Intent.FIND_DEPENDENTS, file_path, project_analysis)
            return ExplanationResult(
                intent=Intent.FIND_DEPENDENTS.value,
                target_file=file_path,
                response=text,
                groq_used=False,
                follow_up_suggestions=suggestions,
            )

        text = await self._groq.find_dependents(
            file_path=file_path,
            dependents=dependents,
            language=lang,
        )
        suggestions = _generate_follow_up_suggestions(Intent.FIND_DEPENDENTS, file_path, project_analysis)
        return ExplanationResult(
            intent=Intent.FIND_DEPENDENTS.value,
            target_file=file_path,
            response=text,
            follow_up_suggestions=suggestions,
        )

    # ── Phase 4: Explain relationship ─────────────────────────────────────────

    async def _explain_relationship(
        self,
        file_a: str,
        file_b: Optional[str],
        project_analysis,
    ) -> ExplanationResult:
        """Read both files and ask Groq to explain how they relate."""
        if not file_b:
            # Only one file — fall back to a combined explain + deps response
            return await self._file_intent(Intent.EXPLAIN_FILE, file_a, project_analysis)

        # Read both files
        try:
            content_a, _ = self._scanner.safe_read(file_a)
        except Exception as exc:
            return ExplanationResult(
                intent=Intent.EXPLAIN_RELATIONSHIP.value,
                target_file=file_a,
                response=f"Could not read `{file_a}`: {exc}",
                error=True,
            )
        try:
            content_b, _ = self._scanner.safe_read(file_b)
        except Exception as exc:
            return ExplanationResult(
                intent=Intent.EXPLAIN_RELATIONSHIP.value,
                target_file=file_a,
                response=f"Could not read `{file_b}`: {exc}",
                error=True,
            )

        deps_a: list[str] = []
        deps_b: list[str] = []
        if project_analysis:
            deps_a = project_analysis.dependencies.entries.get(file_a, [])
            deps_b = project_analysis.dependencies.entries.get(file_b, [])

        lang = _detect_language(file_a)
        text = await self._groq.explain_relationship(
            file_a=file_a,
            file_b=file_b,
            language=lang,
            content_a=content_a,
            content_b=content_b,
            deps_a=deps_a,
            deps_b=deps_b,
        )
        suggestions = [
            f"Explain {file_a.split('/')[-1]}",
            f"Explain {file_b.split('/')[-1]}",
            f"Which files depend on {file_a.split('/')[-1]}?",
            "Show related components",
        ]
        return ExplanationResult(
            intent=Intent.EXPLAIN_RELATIONSHIP.value,
            target_file=file_a,
            response=text,
            follow_up_suggestions=suggestions,
        )

    # ── Phase 4: Show related files ────────────────────────────────────────────

    async def _show_related(
        self,
        file_path: str,
        project_analysis,
    ) -> ExplanationResult:
        """Show forward + reverse deps and ask Groq to summarise the neighbourhood."""
        forward_deps: list[str] = []
        reverse_deps: list[str] = []
        if project_analysis:
            forward_deps = project_analysis.dependencies.entries.get(file_path, [])
            reverse_deps = _reverse_deps(file_path, project_analysis.dependencies.entries)

        lang = _detect_language(file_path)
        text = await self._groq.show_related(
            file_path=file_path,
            language=lang,
            forward_deps=forward_deps,
            reverse_deps=reverse_deps,
        )
        suggestions = _generate_follow_up_suggestions(Intent.SHOW_RELATED, file_path, project_analysis)
        return ExplanationResult(
            intent=Intent.SHOW_RELATED.value,
            target_file=file_path,
            response=text,
            follow_up_suggestions=suggestions,
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


def _reverse_deps(file_path: str, dep_entries: dict[str, list[str]]) -> list[str]:
    """
    Compute reverse dependencies: all files in dep_entries whose dependency
    list contains file_path (matched by suffix to handle path normalisation).
    """
    target_name = Path(file_path).name
    result: list[str] = []
    for src, deps in dep_entries.items():
        for dep in deps:
            if dep == file_path or Path(dep).name == target_name:
                result.append(src)
                break
    return result


def _generate_follow_up_suggestions(
    intent: Intent,
    file_path: Optional[str],
    project_analysis,
) -> list[str]:
    """
    Generate 3–4 contextually relevant follow-up prompts for the current result.
    """
    fname = file_path.split("/")[-1] if file_path else None

    if intent == Intent.EXPLAIN_FILE:
        base = [
            f"Summarize {fname}" if fname else "Summarize this file",
            f"What are the dependencies of {fname}?" if fname else "What are its dependencies?",
            f"Which files depend on {fname}?" if fname else "Which files depend on it?",
            "Show related components",
        ]
    elif intent == Intent.SUMMARIZE_FILE:
        base = [
            f"Explain {fname} in detail" if fname else "Explain this file in detail",
            f"What are the dependencies of {fname}?" if fname else "What are its dependencies?",
            f"Which files depend on {fname}?" if fname else "Which files depend on it?",
            "Show related files",
        ]
    elif intent == Intent.EXPLAIN_DEPENDENCIES:
        base = [
            f"Explain {fname}" if fname else "Explain this file",
            f"Which files depend on {fname}?" if fname else "Which files depend on it?",
            "Show related components",
            "Give me a project overview",
        ]
    elif intent == Intent.FIND_DEPENDENTS:
        base = [
            f"Explain {fname}" if fname else "Explain this file",
            f"Summarize {fname}" if fname else "Summarize this file",
            "Show related files",
            f"What are the dependencies of {fname}?" if fname else "What does it depend on?",
        ]
    elif intent == Intent.SHOW_RELATED:
        base = [
            f"Explain {fname}" if fname else "Explain this file",
            f"Which files depend on {fname}?" if fname else "Which files depend on it?",
            f"What are the dependencies of {fname}?" if fname else "What does it depend on?",
            "Give me a project overview",
        ]
    else:
        # project_overview, explain_relationship, or any other
        base = [
            "Which files have the most dependencies?",
            "Show related components",
            "Explain the main entry point",
        ]
        if fname:
            base.insert(0, f"Explain {fname}")

    return base[:4]
