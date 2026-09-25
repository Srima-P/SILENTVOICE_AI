"""
Assistant API routes — Phase 3.

Endpoints:
  POST /api/assistant/chat  → Classify intent, resolve file, call Groq, return explanation
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
    Pipeline:
      1. Classify intent (deterministic, no LLM)
      2. Resolve file reference against project tree (if needed)
      3. Load project analysis metadata (for context)
      4. Call ExplanationService → GroqService
      5. Return structured response
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

    # 2. Resolve file (if the intent requires one)
    resolved_file: str | None = None
    candidates: list[str] = []

    if classification.is_file_intent and classification.file_reference:
        try:
            scanner = ProjectScanner(settings.project_root_path)
            tree = scanner.scan()
            resolver = FileResolver(tree.children)
            result = resolver.resolve(classification.file_reference)
        except Exception as exc:
            logger.exception("File resolution error")
            return ChatResponse(
                intent=classification.intent.value,
                target_file=None,
                response=f"Could not scan project to resolve file reference: {exc}",
                error=True,
                groq_used=False,
            )

        if result.found:
            resolved_file = result.path
        elif result.candidates:
            # Ambiguous — return clarification request without calling Groq
            return ChatResponse(
                intent=classification.intent.value,
                target_file=None,
                response=result.message,
                error=False,
                candidates=result.candidates,
                groq_used=False,
            )
        else:
            # Not found
            return ChatResponse(
                intent=classification.intent.value,
                target_file=None,
                response=result.message,
                error=True,
                groq_used=False,
            )

    # 3. Load project analysis (best-effort — don't fail the request if absent)
    project_analysis: ProjectAnalysisResponse | None = None
    try:
        project_analysis = await _load_analysis()
    except Exception as exc:
        logger.warning("Could not load project analysis: %s", exc)

    # 4. Delegate to ExplanationService
    svc = ExplanationService()
    explanation = await svc.handle(
        intent=classification.intent,
        resolved_file=resolved_file,
        project_analysis=project_analysis,
    )

    return ChatResponse(
        intent=explanation.intent,
        target_file=explanation.target_file,
        response=explanation.response,
        error=explanation.error,
        candidates=candidates,
        groq_used=explanation.groq_used,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

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
