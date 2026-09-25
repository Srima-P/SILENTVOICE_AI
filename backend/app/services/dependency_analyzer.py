"""
DependencyAnalyzer — static import extraction for JS/TS and Python files.

This is purely lexical/regex-based analysis. It does NOT execute code and
makes no claims about runtime dependency resolution.

Supported patterns:

JavaScript / TypeScript / JSX / TSX:
  import X from "./X"
  import { X } from "./X"
  import * as X from "./X"
  import "./styles.css"
  import type { X } from "./X"
  export { X } from "./X"
  const X = require("./module")
  dynamic import("./module")  (partial)

Python:
  import module
  import module.sub
  from module import something
  from .relative import something
  from ..relative import something
"""
from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath

from app.schemas.project import DependencyMap, FileDependencies

logger = logging.getLogger("silentvoice.deps")

# ─── Regex patterns ───────────────────────────────────────────────────────────

# JS/TS: static import / export ... from "..."
_JS_IMPORT_FROM = re.compile(
    r"""(?:import|export)\s+(?:type\s+)?(?:[\w*{},\s]+\s+from\s+)?['"](\.{1,2}[^'"]+)['"]""",
    re.MULTILINE,
)

# JS/TS: bare import "..."  (side-effect import)
_JS_BARE_IMPORT = re.compile(
    r"""import\s+['"](\.[^'"]+)['"]""",
    re.MULTILINE,
)

# JS/TS: require("...")
_JS_REQUIRE = re.compile(
    r"""require\s*\(\s*['"](\.[^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

# Python: from .x import ... / from ..x import ...
_PY_RELATIVE = re.compile(
    r"""^from\s+(\.+\w*(?:\.\w+)*)\s+import""",
    re.MULTILINE,
)

# Python: import x.y.z
_PY_ABSOLUTE = re.compile(
    r"""^import\s+([\w.]+)""",
    re.MULTILINE,
)

# Python: from x.y import z  (absolute, for module-level detection)
_PY_FROM_ABS = re.compile(
    r"""^from\s+([\w][\w.]*)\s+import""",
    re.MULTILINE,
)

# JS/TS extensions to try when resolving bare module names
_JS_EXTENSIONS = [".js", ".jsx", ".ts", ".tsx", ".css", ".json"]
_PY_EXTENSIONS = [".py"]


# ─── Helper: resolve a JS/TS import specifier to a project-relative path ─────

def _resolve_js_import(
    source_path: str,
    import_spec: str,
    root: Path,
) -> str | None:
    """
    Try to resolve a relative JS/TS import specifier to a project file path.

    Returns the resolved posix path string relative to root, or None if
    the file cannot be found.
    """
    if not import_spec.startswith("."):
        return None  # External / node_modules — skip

    source_dir = (root / source_path).parent
    candidate_base = (source_dir / import_spec).resolve()

    # Try exact path first
    if candidate_base.is_file():
        try:
            return candidate_base.relative_to(root).as_posix()
        except ValueError:
            return None

    # Try adding extensions
    for ext in _JS_EXTENSIONS:
        candidate = candidate_base.with_suffix(ext)
        if candidate.is_file():
            try:
                return candidate.relative_to(root).as_posix()
            except ValueError:
                return None
        # Try index file
        index = candidate_base / f"index{ext}"
        if index.is_file():
            try:
                return index.relative_to(root).as_posix()
            except ValueError:
                return None

    return None


def _resolve_py_relative(
    source_path: str,
    dots: str,
    module: str,
    root: Path,
) -> str | None:
    """
    Resolve a Python relative import like ``from ..utils import x``.
    Returns project-relative posix path or None.
    """
    levels = len(dots)
    source_dir = (root / source_path).parent
    # Go up `levels` directories
    base = source_dir
    for _ in range(levels - 1):
        base = base.parent

    if module:
        parts = module.split(".")
        candidate = base.joinpath(*parts)
    else:
        candidate = base

    for ext in _PY_EXTENSIONS:
        f = candidate.with_suffix(ext)
        if f.is_file():
            try:
                return f.relative_to(root).as_posix()
            except ValueError:
                return None
        init = candidate / f"__init__{ext}"
        if init.is_file():
            try:
                return init.relative_to(root).as_posix()
            except ValueError:
                return None

    return None


# ─── Per-file extractor ───────────────────────────────────────────────────────

def _extract_js_imports(content: str, file_path: str, root: Path) -> FileDependencies:
    raw: list[str] = []
    resolved: list[str] = []
    unresolved: list[str] = []

    specs: list[str] = []
    specs.extend(_JS_IMPORT_FROM.findall(content))
    specs.extend(_JS_BARE_IMPORT.findall(content))
    specs.extend(_JS_REQUIRE.findall(content))

    # Deduplicate while preserving order
    seen: set[str] = set()
    for spec in specs:
        spec = spec.strip()
        if spec not in seen:
            seen.add(spec)
            raw.append(spec)

    for spec in raw:
        r = _resolve_js_import(file_path, spec, root)
        if r:
            resolved.append(r)
        else:
            unresolved.append(spec)

    return FileDependencies(
        file_path=file_path,
        raw_imports=raw,
        resolved_imports=resolved,
    )


def _extract_py_imports(content: str, file_path: str, root: Path) -> FileDependencies:
    raw: list[str] = []
    resolved: list[str] = []
    unresolved: list[str] = []

    # Relative imports
    for m in _PY_RELATIVE.finditer(content):
        spec = m.group(1)
        dots = ""
        rest = ""
        for ch in spec:
            if ch == ".":
                dots += "."
            else:
                rest = spec[len(dots):]
                break
        raw.append(spec)
        r = _resolve_py_relative(file_path, dots, rest, root)
        if r:
            resolved.append(r)
        else:
            unresolved.append(spec)

    # Absolute imports — record raw, mark unresolved (external packages)
    for m in _PY_ABSOLUTE.finditer(content):
        spec = m.group(1)
        if spec not in raw:
            raw.append(spec)
            unresolved.append(spec)

    for m in _PY_FROM_ABS.finditer(content):
        spec = m.group(1)
        if spec not in raw:
            raw.append(spec)
            unresolved.append(spec)

    return FileDependencies(
        file_path=file_path,
        raw_imports=raw,
        resolved_imports=resolved,
    )


# ─── Analyzer class ───────────────────────────────────────────────────────────

_JS_LIKE = {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"}
_PY_LIKE = {".py"}


class DependencyAnalyzer:
    """
    Analyses import statements across a project and builds a dependency map.

    Usage:
        analyzer = DependencyAnalyzer(root_path)
        dep_map = analyzer.analyze(file_list)
    """

    def __init__(self, root_path: str | Path) -> None:
        self.root = Path(root_path).resolve()

    def analyze_file(self, relative_path: str, content: str) -> FileDependencies:
        """
        Extract imports from a single file.

        :param relative_path: posix path relative to project root
        :param content: UTF-8 source text
        """
        ext = Path(relative_path).suffix.lower()

        if ext in _JS_LIKE:
            return _extract_js_imports(content, relative_path, self.root)
        elif ext in _PY_LIKE:
            return _extract_py_imports(content, relative_path, self.root)
        else:
            return FileDependencies(file_path=relative_path)

    def analyze_project(
        self,
        source_files: list[tuple[str, str]],
    ) -> DependencyMap:
        """
        Build a full project dependency map.

        :param source_files: list of (relative_path, content) tuples
        :returns: DependencyMap with resolved and unresolved entries
        """
        entries: dict[str, list[str]] = {}
        unresolved: dict[str, list[str]] = {}

        for rel_path, content in source_files:
            try:
                deps = self.analyze_file(rel_path, content)
            except Exception as exc:
                logger.warning("Dependency analysis failed for %s: %s", rel_path, exc)
                continue

            if deps.resolved_imports:
                entries[rel_path] = deps.resolved_imports
            if deps.raw_imports:
                ur = [
                    r
                    for r in deps.raw_imports
                    if r not in deps.resolved_imports
                ]
                if ur:
                    unresolved[rel_path] = ur

        return DependencyMap(entries=entries, unresolved=unresolved)


def detect_react_components(
    source_files: list[tuple[str, str]],
) -> list[dict[str, str]]:
    """
    Identify likely React component files using naming conventions and
    JSX/TSX heuristics.

    Returns list of dicts: {name, path, type}.
    """
    components: list[dict[str, str]] = []
    jsx_exts = {".jsx", ".tsx"}

    # Heuristic: detect JSX return / React.createElement
    _has_jsx = re.compile(
        r"""return\s*\(?\s*<[A-Z][A-Za-z]*|React\.createElement|<[A-Z][A-Za-z]*\s""",
    )
    # Also: default export of a PascalCase function
    _default_export = re.compile(
        r"""export\s+default\s+(?:function\s+)?([A-Z][A-Za-z0-9]*)"""
    )

    for rel_path, content in source_files:
        ext = Path(rel_path).suffix.lower()
        if ext not in jsx_exts:
            continue

        name = Path(rel_path).stem
        # PascalCase filename is a strong signal
        is_pascal = name[0].isupper() if name else False
        has_jsx_content = bool(_has_jsx.search(content))
        has_default_export = _default_export.search(content)

        if is_pascal or has_jsx_content or has_default_export:
            component_name = name
            if has_default_export:
                component_name = has_default_export.group(1)
            components.append(
                {
                    "name": component_name,
                    "path": rel_path,
                    "type": "react_component",
                }
            )

    return components
