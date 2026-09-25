"""
FileResolver — maps a user's file mention to a real project path.

Given a reference like "Login.jsx" or "components/Login" it searches the
project file tree and returns the best match.

Handles:
  • Exact filename match
  • Case-insensitive filename match
  • Partial path match  (e.g. "components/Login.jsx" → "src/components/Login.jsx")
  • Extension-less match (e.g. "Login" → "Login.jsx" / "Login.tsx")
  • Multiple matches → returns all candidates for clarification
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional


@dataclass
class ResolveResult:
    """Outcome of a file-resolution attempt."""
    found: bool
    path: Optional[str]                   # best single match (relative to project root)
    candidates: list[str]                 # all matches when ambiguous
    message: str                          # human-readable status


def _collect_files(tree: list[dict]) -> list[str]:
    """
    Walk a FileNodeSchema-style tree (list of dicts with 'type'/'path'/'children')
    and return all file paths.
    Works with both dict objects (from JSON) and Pydantic model instances.
    """
    result: list[str] = []

    def _walk(nodes: list) -> None:
        for node in nodes:
            # Support both dict and Pydantic-style objects
            if isinstance(node, dict):
                t = node.get("type", "")
                p = node.get("path", "")
                children = node.get("children") or []
            else:
                t = getattr(node, "type", "")
                p = getattr(node, "path", "")
                children = getattr(node, "children", None) or []

            if t == "file":
                result.append(p)
            elif t == "directory":
                _walk(children)

    _walk(tree)
    return result


class FileResolver:
    """
    Resolves a user-provided file reference to a path in the project tree.

    Usage:
        resolver = FileResolver(project_tree_nodes)
        result = resolver.resolve("Login.jsx")
    """

    def __init__(self, tree_nodes: list) -> None:
        self._all_files: list[str] = _collect_files(tree_nodes)

    def resolve(self, reference: str) -> ResolveResult:
        """
        Attempt to resolve *reference* to a project file path.

        Returns a ResolveResult describing the outcome.
        """
        if not reference or not reference.strip():
            return ResolveResult(
                found=False,
                path=None,
                candidates=[],
                message="No file reference provided.",
            )

        ref = reference.strip().replace("\\", "/")
        candidates = self._find_candidates(ref)

        if not candidates:
            return ResolveResult(
                found=False,
                path=None,
                candidates=[],
                message=f"No file matching '{reference}' was found in the project.",
            )

        if len(candidates) == 1:
            return ResolveResult(
                found=True,
                path=candidates[0],
                candidates=candidates,
                message=f"Resolved to: {candidates[0]}",
            )

        # Multiple matches — ask user to clarify
        bullet_list = "\n".join(f"  - {c}" for c in candidates)
        return ResolveResult(
            found=False,
            path=None,
            candidates=candidates,
            message=(
                f"Multiple files match '{reference}':\n{bullet_list}\n"
                "Please be more specific, e.g. include the full path."
            ),
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _find_candidates(self, ref: str) -> list[str]:
        """Return all project file paths that match the reference."""
        ref_lower = ref.lower()
        ref_name = PurePosixPath(ref).name.lower()   # just the filename part
        ref_stem = PurePosixPath(ref).stem.lower()   # filename without extension
        ref_has_ext = "." in PurePosixPath(ref).name

        matches: list[str] = []

        for fp in self._all_files:
            fp_lower = fp.lower()
            fp_name = PurePosixPath(fp).name.lower()
            fp_stem = PurePosixPath(fp).stem.lower()

            # Strategy 1: exact path match (case-insensitive)
            if fp_lower == ref_lower or fp_lower.endswith("/" + ref_lower):
                matches.append(fp)
                continue

            # Strategy 2: filename match (case-insensitive)
            if fp_name == ref_name:
                matches.append(fp)
                continue

            # Strategy 3: extension-less match
            if not ref_has_ext and fp_stem == ref_stem:
                matches.append(fp)
                continue

            # Strategy 4: ref is a partial path suffix
            # e.g. "components/Login.jsx" matches "src/components/Login.jsx"
            if ref_lower in fp_lower and "/" in ref_lower:
                matches.append(fp)
                continue

        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                deduped.append(m)

        # Prefer shorter paths (more specific) — sort ascending by path depth
        deduped.sort(key=lambda p: (len(p.split("/")), p))
        return deduped
