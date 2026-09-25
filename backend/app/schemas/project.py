"""
Phase 2 schemas — Project scanning, file reading, and dependency analysis.

All responses from the project API are typed here.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ─── File / Directory Tree ────────────────────────────────────────────────────

class FileNodeSchema(BaseModel):
    """A single node in the project file tree (file or directory)."""

    name: str = Field(..., description="Base name of the file or directory")
    path: str = Field(..., description="Path relative to the project root")
    type: str = Field(..., description="'file' or 'directory'")
    language: Optional[str] = Field(None, description="Detected language for files")
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    children: Optional[list["FileNodeSchema"]] = Field(
        None, description="Child nodes (directories only)"
    )


FileNodeSchema.model_rebuild()


class ProjectTreeResponse(BaseModel):
    """Response for GET /api/project/tree"""

    name: str
    # root_path intentionally excluded from client responses — server-side only.
    # Stored internally so ProjectScanner.scan() can populate it, but excluded
    # from JSON serialization via exclude=True.
    root_path: Optional[str] = Field(
        None,
        exclude=True,
        description="Resolved absolute project root (server-side only, never sent to client)",
    )
    type: str = "directory"
    total_files: int
    total_dirs: int
    children: list[FileNodeSchema]


# ─── File Reading ─────────────────────────────────────────────────────────────

class FileReadResponse(BaseModel):
    """Response for GET /api/project/file"""

    path: str = Field(..., description="Relative path from project root")
    name: str
    language: str
    size_bytes: int
    lines: int
    content: str
    encoding: str = "utf-8"


# ─── Dependency Analysis ──────────────────────────────────────────────────────

class FileDependencies(BaseModel):
    """Import dependencies for a single file."""

    file_path: str
    raw_imports: list[str] = Field(
        default_factory=list,
        description="Raw import strings extracted from source",
    )
    resolved_imports: list[str] = Field(
        default_factory=list,
        description="Relative paths resolved to project files",
    )


class DependencyMap(BaseModel):
    """Full project dependency map."""

    entries: dict[str, list[str]] = Field(
        default_factory=dict,
        description="file_path → list of resolved dependency paths",
    )
    unresolved: dict[str, list[str]] = Field(
        default_factory=dict,
        description="file_path → list of raw imports that could not be resolved",
    )


# ─── Project Analysis ─────────────────────────────────────────────────────────

class ComponentInfo(BaseModel):
    """A detected component/class/module."""

    name: str
    path: str
    type: str = Field(..., description="'react_component' | 'python_module' | 'class'")


class ProjectAnalysisResponse(BaseModel):
    """Response for GET /api/project/analyze"""

    project_name: str
    # root_path is kept for internal service use (e.g. path resolution in
    # ExplanationService) but is excluded from all JSON responses sent to clients.
    root_path: Optional[str] = Field(
        None,
        exclude=True,
        description="Absolute project root — internal use only, never serialized to client",
    )
    total_files: int
    source_files: int
    languages: dict[str, int] = Field(
        default_factory=dict,
        description="language → file count",
    )
    components: list[ComponentInfo] = Field(default_factory=list)
    dependencies: DependencyMap = Field(default_factory=DependencyMap)
    scan_errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal errors encountered during scan",
    )
