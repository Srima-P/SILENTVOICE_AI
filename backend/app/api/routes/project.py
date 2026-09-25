"""
Project API routes — Phase 2.

Endpoints:
  GET /api/project/tree     → Scanned project file tree
  GET /api/project/file     → Read a single source file (safe)
  GET /api/project/analyze  → Full project analysis (stats + deps)
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.schemas.project import (
    FileReadResponse,
    ProjectAnalysisResponse,
    ProjectTreeResponse,
    ComponentInfo,
    DependencyMap,
)
from app.services.project_scanner import ProjectScanner, _detect_language
from app.services.dependency_analyzer import (
    DependencyAnalyzer,
    detect_react_components,
)

router = APIRouter()
logger = logging.getLogger("silentvoice.api.project")


# ─── Shared scanner factory ───────────────────────────────────────────────────

def _get_root() -> Path:
    """Resolve and validate the configured project root."""
    root = settings.project_root_path
    if not root:
        raise HTTPException(
            status_code=503,
            detail="No PROJECT_ROOT configured on the backend. "
                   "Set PROJECT_ROOT in your .env file.",
        )
    p = Path(root).resolve()
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Configured project root does not exist: {root!r}",
        )
    if not p.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Configured PROJECT_ROOT is not a directory: {root!r}",
        )
    return p


# ─── GET /api/project/tree ────────────────────────────────────────────────────

@router.get(
    "/tree",
    response_model=ProjectTreeResponse,
    summary="Scan and return the project file tree",
)
async def get_project_tree() -> ProjectTreeResponse:
    """
    Recursively scans the configured project root and returns the file tree.
    Ignores node_modules, __pycache__, .git, secret files, and binaries.
    """
    root = _get_root()
    scanner = ProjectScanner(root)

    try:
        tree = scanner.scan()
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during project scan")
        raise HTTPException(status_code=500, detail="Project scan failed.")

    if scanner.errors:
        logger.warning("Scan completed with %d non-fatal errors", len(scanner.errors))

    return tree


# ─── GET /api/project/file ────────────────────────────────────────────────────

@router.get(
    "/file",
    response_model=FileReadResponse,
    summary="Read a source file from the project",
)
async def get_project_file(
    path: str = Query(
        ...,
        description="Relative path from the project root, e.g. src/App.jsx",
        min_length=1,
        max_length=512,
    )
) -> FileReadResponse:
    """
    Returns the content of a project file identified by its relative path.

    Security:
    - Path traversal (../) is rejected.
    - Access outside the project root is rejected.
    - Secret / sensitive files are rejected.
    - Binary and oversized files are rejected.
    """
    root = _get_root()
    scanner = ProjectScanner(root)

    try:
        content, line_count = scanner.safe_read(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Permission denied: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error reading file %r", path)
        raise HTTPException(status_code=500, detail="Failed to read file.")

    clean = path.lstrip("/\\")
    file_path = Path(clean)
    size = (root / clean).stat().st_size

    return FileReadResponse(
        path=clean,
        name=file_path.name,
        language=_detect_language(file_path),
        size_bytes=size,
        lines=line_count,
        content=content,
    )


# ─── GET /api/project/analyze ─────────────────────────────────────────────────

@router.get(
    "/analyze",
    response_model=ProjectAnalysisResponse,
    summary="Full project analysis: stats, language breakdown, dependencies",
)
async def analyze_project() -> ProjectAnalysisResponse:
    """
    Performs a full project scan followed by dependency and component analysis.

    Returns:
    - File and directory counts
    - Language breakdown
    - Detected React components / Python modules
    - Static import dependency map
    - Non-fatal scan errors
    """
    root = _get_root()
    scanner = ProjectScanner(root)

    try:
        tree = scanner.scan()
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error during analysis scan")
        raise HTTPException(status_code=500, detail="Project analysis failed.")

    # ── Collect all source files ──────────────────────────────────────────────
    language_counts: dict[str, int] = {}
    source_files: list[tuple[str, str]] = []  # (rel_path, content)

    def _collect(nodes: list) -> None:
        for node in nodes:
            if node.type == "file":
                lang = node.language or "text"
                language_counts[lang] = language_counts.get(lang, 0) + 1
                # Read content for dependency analysis (best-effort)
                try:
                    content, _ = scanner.safe_read(node.path)
                    source_files.append((node.path, content))
                except Exception as exc:
                    logger.debug("Skipping %s for analysis: %s", node.path, exc)
            elif node.type == "directory" and node.children:
                _collect(node.children)

    _collect(tree.children)

    # ── Dependency analysis ───────────────────────────────────────────────────
    analyzer = DependencyAnalyzer(root)
    dep_map = analyzer.analyze_project(source_files)

    # ── Component detection ───────────────────────────────────────────────────
    raw_components = detect_react_components(source_files)
    components = [
        ComponentInfo(name=c["name"], path=c["path"], type=c["type"])
        for c in raw_components
    ]

    return ProjectAnalysisResponse(
        project_name=tree.name,
        root_path=str(root),
        total_files=tree.total_files,
        source_files=len(source_files),
        languages=language_counts,
        components=components,
        dependencies=dep_map,
        scan_errors=scanner.errors,
    )
