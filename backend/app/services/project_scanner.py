"""
ProjectScanner — safely scans a local project directory.

Security guarantees:
  • All resolved paths are checked to be inside the project root.
  • Secret / sensitive files are never included.
  • Binary files and over-sized files are skipped gracefully.
  • Encoding errors are handled without crashing.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from app.schemas.project import FileNodeSchema, ProjectTreeResponse

logger = logging.getLogger("silentvoice.scanner")

# ─── Configuration constants ──────────────────────────────────────────────────

# Directories that are always ignored (by name, at any depth)
IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "env",
        ".env",           # a directory named .env
        "dist",
        "build",
        "out",
        ".next",
        ".nuxt",
        "coverage",
        "htmlcov",
        ".tox",
        ".eggs",
        "*.egg-info",
    }
)

# Files that are never returned to the client (exact names or glob patterns)
SECRET_FILES: frozenset[str] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.development",
        ".env.production",
        ".env.test",
        ".env.example",   # could contain real values
        ".envrc",
        "secrets.json",
        "credentials.json",
        "service-account.json",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "id_rsa",
        "id_ed25519",
        ".netrc",
        ".npmrc",         # may contain auth tokens
        ".pypirc",
    }
)

# Allowed source-code / text file extensions
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".json",
        ".jsonc",
        ".md",
        ".mdx",
        ".txt",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".sql",
        ".graphql",
        ".gql",
        ".xml",
        ".svg",
        ".vue",
        ".svelte",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".rb",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".Dockerfile",
        "",  # files without extension (e.g., Makefile, Dockerfile)
    }
)

# Extension → language label mapping
LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    ".json": "json",
    ".jsonc": "json",
    ".md": "markdown",
    ".mdx": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".xml": "xml",
    ".svg": "xml",
    ".vue": "vue",
    ".svelte": "svelte",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
}

# Files above this size are skipped (default 1 MB)
MAX_FILE_BYTES: int = 1 * 1024 * 1024


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_secret_file(name: str) -> bool:
    """Return True if the file name matches a secret-file pattern."""
    # Exact match
    if name in SECRET_FILES:
        return True
    # Check .env.* prefix
    if name.startswith(".env"):
        return True
    # Extension-based secrets
    _, ext = os.path.splitext(name)
    if ext in {".pem", ".key", ".p12", ".pfx"}:
        return True
    return False


def _should_ignore_dir(name: str) -> bool:
    """Return True if this directory should be excluded from scanning."""
    if name in IGNORED_DIRS:
        return True
    # Ignore hidden directories (starting with .) except for known useful ones
    if name.startswith(".") and name not in {".github", ".vscode"}:
        return True
    return False


def _detect_language(path: Path) -> str:
    """Detect the language label from the file extension."""
    ext = path.suffix.lower()
    # Special case: files with no extension but known names
    if not ext:
        name_lower = path.name.lower()
        if name_lower in {"makefile", "dockerfile", "vagrantfile", "rakefile"}:
            return "shell"
        return "text"
    return LANGUAGE_MAP.get(ext, "text")


def _is_allowed_file(path: Path) -> bool:
    """Return True if this file should be included in the tree."""
    if _is_secret_file(path.name):
        return False
    ext = path.suffix.lower()
    # Allow files with known extensions OR no extension (e.g., Makefile)
    if ext in ALLOWED_EXTENSIONS:
        return True
    if not ext and path.name[0] != ".":
        return True
    return False


# ─── Scanner ──────────────────────────────────────────────────────────────────

class ProjectScanner:
    """
    Recursively scans a project directory and builds a FileNodeSchema tree.

    Usage:
        scanner = ProjectScanner(root_path)
        tree = scanner.scan()
    """

    def __init__(self, root_path: str | Path) -> None:
        self.root = Path(root_path).resolve()
        self._errors: list[str] = []
        self._file_count: int = 0
        self._dir_count: int = 0

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def _assert_root_exists(self) -> None:
        if not self.root.exists():
            raise FileNotFoundError(f"Project root does not exist: {self.root}")
        if not self.root.is_dir():
            raise NotADirectoryError(f"Project root is not a directory: {self.root}")

    def scan(self) -> ProjectTreeResponse:
        """
        Perform a full recursive scan and return the project tree.
        Raises FileNotFoundError / NotADirectoryError for invalid roots.
        """
        self._assert_root_exists()
        self._errors = []
        self._file_count = 0
        self._dir_count = 0

        children = self._scan_dir(self.root)

        return ProjectTreeResponse(
            name=self.root.name,
            root_path=str(self.root),
            type="directory",
            total_files=self._file_count,
            total_dirs=self._dir_count,
            children=children,
        )

    def _scan_dir(self, directory: Path) -> list[FileNodeSchema]:
        """Recursively scan a directory and return its children."""
        nodes: list[FileNodeSchema] = []

        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError as exc:
            self._errors.append(f"Permission denied: {exc}")
            return nodes
        except OSError as exc:
            self._errors.append(f"OS error reading {directory}: {exc}")
            return nodes

        for entry in entries:
            rel = entry.relative_to(self.root)
            rel_str = rel.as_posix()

            if entry.is_symlink():
                # Skip symlinks to avoid cycles or out-of-root access
                continue

            if entry.is_dir():
                if _should_ignore_dir(entry.name):
                    continue
                self._dir_count += 1
                child_nodes = self._scan_dir(entry)
                nodes.append(
                    FileNodeSchema(
                        name=entry.name,
                        path=rel_str,
                        type="directory",
                        children=child_nodes,
                    )
                )

            elif entry.is_file():
                if not _is_allowed_file(entry):
                    continue

                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0

                if size > MAX_FILE_BYTES:
                    self._errors.append(
                        f"Skipped (too large, {size} bytes): {rel_str}"
                    )
                    continue

                self._file_count += 1
                lang = _detect_language(entry)
                nodes.append(
                    FileNodeSchema(
                        name=entry.name,
                        path=rel_str,
                        type="file",
                        language=lang,
                        size_bytes=size,
                    )
                )

        return nodes

    # ─── Safe file reading ────────────────────────────────────────────────────

    def safe_read(self, relative_path: str) -> tuple[str, int]:
        """
        Read a file identified by *relative_path* (relative to project root).

        Returns (content, line_count).
        Raises:
            ValueError   — path traversal or disallowed extension
            FileNotFoundError — file does not exist
            PermissionError — access denied
            UnicodeDecodeError — binary / non-UTF-8 file (re-raised as ValueError)
        """
        # --- Security: normalize and validate ---
        # Reject absolute paths outright (covers both POSIX and Windows drive letters)
        if Path(relative_path).is_absolute():
            raise ValueError(f"Absolute paths are not accepted: {relative_path!r}")
        # Strip leading separators so Path() doesn't treat it as absolute
        clean = relative_path.lstrip("/\\")
        # Reject obvious traversal fragments
        if ".." in clean.split("/") or ".." in clean.split("\\"):
            raise ValueError(f"Path traversal attempt detected: {relative_path!r}")

        try:
            target = (self.root / clean).resolve()
        except Exception as exc:
            raise ValueError(f"Invalid path: {relative_path!r}") from exc

        # Ensure resolved path stays inside the project root
        try:
            target.relative_to(self.root)
        except ValueError:
            raise ValueError(
                f"Path escapes project root: {relative_path!r}"
            )

        if not target.exists():
            raise FileNotFoundError(f"File not found: {relative_path!r}")

        if not target.is_file():
            raise ValueError(f"Not a regular file: {relative_path!r}")

        # Check secret / disallowed
        if _is_secret_file(target.name):
            raise ValueError(f"Access to sensitive file denied: {target.name!r}")

        if not _is_allowed_file(target):
            raise ValueError(
                f"File type not allowed: {target.suffix!r}"
            )

        size = target.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError(
                f"File too large ({size} bytes). Maximum is {MAX_FILE_BYTES} bytes."
            )

        try:
            content = target.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            raise ValueError(f"File is binary or uses a non-UTF-8 encoding: {relative_path!r}")

        lines = content.splitlines()
        return content, len(lines)


def get_scanner(root_path: str | Path) -> ProjectScanner:
    """Factory function — creates and returns a scanner for the given root."""
    return ProjectScanner(root_path)
