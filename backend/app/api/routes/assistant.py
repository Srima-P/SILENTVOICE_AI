"""
Assistant API routes — Phase 4.

Endpoints:
  POST /api/assistant/chat  → Classify intent, resolve context, call Groq, return explanation
  GET  /api/assistant/status → Whether Groq is configured
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.schemas.assistant import ChatRequest, ChatResponse
from app.schemas.project import ProjectAnalysisResponse
from app.services.intent_classifier import classify, Intent
from app.services.file_resolver import FileResolver
from app.services.explanation_service import ExplanationService
from app.services.project_scanner import ProjectScanner
from app.services.dependency_analyzer import DependencyAnalyzer, detect_react_components
from app.services.conversation_manager import ConversationManager

router = APIRouter()
logger = logging.getLogger("silentvoice.api.assistant")


# ── GET /api/assistant/status ─────────────────────────────────────────────────

@router.get("/status", summary="Check if the AI assistant is configured")
async def assistant_status() -> dict:
    """Returns whether GROQ_API_KEY is set (without exposing the key)."""
    return {
        "groq_configured": bool(settings.groq_api_key and settings.groq_api_key.strip()),
        "model": settings.groq_model,
    }


# ── POST /api/assistant/chat ──────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a natural-language message to the AI assistant",
)
async def chat(body: ChatRequest) -> ChatResponse:
    """
    Phase 4 pipeline:
      1. Classify intent (deterministic, no LLM)
      2. Build project file tree for context resolution
      3. Use ConversationManager to resolve the active file from:
           a. Explicit file reference in the message
           b. selected_file passed from the frontend (Project Explorer selection)
           c. Last file discussed in conversation_history
      4. Extract second file reference (for relationship queries)
      5. Load project analysis metadata (best-effort)
      6. Call ExplanationService → GroqService
      7. Return structured response with follow_up_suggestions
    """
    logger.info("Chat request: %r", body.message[:120])

    # 1. Classify intent
    classification = classify(body.message)
    logger.info(
        "Intent: %s  file_ref: %r  confidence: %.2f",
        classification.intent,
        classification.file_reference,
        classification.confidence,
    )

    # 2. Build project tree for resolver
    tree_nodes: list = []
    try:
        scanner = ProjectScanner(settings.project_root_path)
        tree = scanner.scan()
        tree_nodes = _flatten_to_raw(tree.children)
    except Exception as exc:
        logger.warning("Could not build project tree for context resolution: %s", exc)

    # 3. Resolve active file via ConversationManager
    manager = ConversationManager(tree_nodes if tree_nodes else None)
    ctx = manager.resolve_context(
        message=body.message,
        selected_file=body.selected_file,
        conversation_history=body.conversation_history,
    )

    resolved_file: str | None = ctx.resolved_file
    context_source: str = ctx.context_source

    logger.info(
        "Context resolution: source=%s  resolved_file=%r  candidates=%r",
        context_source,
        resolved_file,
        ctx.candidates,
    )

    # Ambiguous file reference — return clarification to the user
    if ctx.candidates:
        return ChatResponse(
            intent=classification.intent.value,
            target_file=None,
            response=(
                f"I found multiple files matching your reference. "
                f"Which one did you mean?\n\n"
                + "\n".join(f"- `{c}`" for c in ctx.candidates)
            ),
            error=False,
            candidates=ctx.candidates,
            groq_used=False,
            context_source=context_source,
        )

    # Explicit ref present but not found in project
    if (
        context_source == "explicit"
        and not resolved_file
        and classification.file_reference
    ):
        return ChatResponse(
            intent=classification.intent.value,
            target_file=None,
            response=f"No file matching `{classification.file_reference}` was found in the project.",
            error=True,
            groq_used=False,
            context_source=context_source,
        )

    # 4. Extract second file for relationship queries
    second_file: str | None = None
    if classification.intent == Intent.EXPLAIN_RELATIONSHIP:
        raw_second = manager.extract_second_file(body.message)
        if raw_second:
            resolver = FileResolver(tree_nodes) if tree_nodes else None
            if resolver:
                r2 = resolver.resolve(raw_second)
                second_file = r2.path if r2.found else raw_second
            else:
                second_file = raw_second

    # 5. Load project analysis (best-effort)
    project_analysis: ProjectAnalysisResponse | None = None
    try:
        project_analysis = await _load_analysis()
    except Exception as exc:
        logger.warning("Could not load project analysis: %s", exc)

    # 6. Delegate to ExplanationService
    svc = ExplanationService()
    explanation = await svc.handle(
        intent=classification.intent,
        resolved_file=resolved_file,
        project_analysis=project_analysis,
        second_file=second_file,
    )

    return ChatResponse(
        intent=explanation.intent,
        target_file=explanation.target_file,
        response=explanation.response,
        error=explanation.error,
        candidates=[],
        groq_used=explanation.groq_used,
        follow_up_suggestions=explanation.follow_up_suggestions,
        context_source=context_source,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flatten_to_raw(nodes: list) -> list:
    """Convert FileNode objects (or dicts) into raw dict format for FileResolver."""
    result = []
    for node in nodes:
        if hasattr(node, "__dict__"):
            raw = {
                "type": node.type,
                "name": node.name,
                "path": node.path,
            }
            if hasattr(node, "children") and node.children:
                raw["children"] = _flatten_to_raw(node.children)
        else:
            raw = node
        result.append(raw)
    return result


async def _load_analysis() -> ProjectAnalysisResponse:
    """
    Run a quick project scan + analysis to get dependency metadata.
    This is intentionally lightweight — we only read files we need for context.
    """
    scanner = ProjectScanner(settings.project_root_path)
    tree = scanner.scan()

    language_counts: dict[str, int] = {}
    source_files: list[tuple[str, str]] = []

    def _collect(nodes: list) -> None:
        for node in nodes:
            if node.type == "file":
                lang = node.language or "text"
                language_counts[lang] = language_counts.get(lang, 0) + 1
                try:
                    content, _ = scanner.safe_read(node.path)
                    source_files.append((node.path, content))
                except Exception:
                    pass
            elif node.type == "directory" and node.children:
                _collect(node.children)

    _collect(tree.children)

    analyzer = DependencyAnalyzer(settings.project_root_path)
    dep_map = analyzer.analyze_project(source_files)
    raw_components = detect_react_components(source_files)

    from app.schemas.project import ComponentInfo, DependencyMap
    return ProjectAnalysisResponse(
        project_name=tree.name,
        root_path=str(scanner.root),
        total_files=tree.total_files,
        source_files=len(source_files),
        languages=language_counts,
        components=[
            ComponentInfo(name=c["name"], path=c["path"], type=c["type"])
            for c in raw_components
        ],
        dependencies=DependencyMap(
            entries=dep_map.entries,
            unresolved=dep_map.unresolved,
        ),
        scan_errors=scanner.errors,
    )
