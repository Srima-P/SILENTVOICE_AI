"""
path_security.py — write-path validation helpers for Phase 6.

Provides independent protection for the code-modification pipeline.
These functions are NEVER called by ProjectScanner or safe_read — they exist
solely for the write path (propose + apply) and are imported by:
  - app.services.code_modification_service  (at propose time)
  - app.api.routes.changes                  (at apply time)

Design principles:
  • All validation happens before any filesystem write.
  • Protected-file list is maintained independently of ProjectScanner.SECRET_FILES
    so that a future refactor of the scanner cannot accidentally weaken write-path
    security.
  • Two complementary check strategies:
      1. fnmatch against the filename (Path.name) — for glob patterns and exact names.
      2. str.startswith against the normalised relative path — for directory prefixes.
  • _validate_write_target is called TWICE per apply (once at propose-time by the
    service, once at apply-time by the route) to catch any filesystem state change
    between the two operations.
"""
from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

logger = logging.getLogger("silentvoice.path_security")

# ── Protected filename patterns ───────────────────────────────────────────────
# Matched against Path(rel_path).name using fnmatch (case-sensitive on POSIX,
# case-insensitive on Windows via fnmatch's platform behaviour).
#
# Rationale for each entry:
#   .env / .env.*   — environment variable files; may contain secrets
#   .envrc          — direnv config; may set secrets in the shell environment
#   secrets.json    — common secret-store file name
#   credentials.json — common GCP / AWS credential file name
#   service-account.json — GCP service account key
#   .netrc          — stores FTP/HTTP credentials
#   .npmrc          — npm token / registry auth
#   .pypirc         — PyPI upload token
#   id_rsa          — SSH private key (RSA)
#   id_ed25519      — SSH private key (Ed25519)
#   *.pem           — PEM-encoded certificates/keys
#   *.key           — private key files (generic)
#   *.p12           — PKCS#12 keystore
#   *.pfx           — Windows personal information exchange (keystore)
#   *.secret        — generic secret-file convention
_PROTECTED_NAME_PATTERNS: list[str] = [
    ".env",
    ".envrc",
    "secrets.json",
    "credentials.json",
    "service-account.json",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.secret",
]

# ── Protected directory prefixes ──────────────────────────────────────────────
# Matched using rel_path.startswith(prefix) after forward-slash normalisation.
# A trailing "/" is required so that a file named "node_modules.py" is NOT blocked.
_PROTECTED_DIR_PREFIXES: list[str] = [
    ".git/",
    "node_modules/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "dist/",
    "build/",
    ".svn/",
    ".hg/",
]


# ── Public exception ──────────────────────────────────────────────────────────

class ProtectedFileError(ValueError):
    """
    Raised when a write target matches a protected file or directory pattern.

    Inherits from ValueError so that callers which already catch ValueError
    (e.g. for path-traversal errors) will also handle this case.  Route handlers
    can additionally catch ProtectedFileError specifically to return HTTP 400.
    """


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_protected(rel_path: str) -> None:
    """
    Raise ProtectedFileError if *rel_path* (path relative to the project root,
    with forward-slash separators) matches any protected pattern.

    Three complementary strategies, applied in order:

    1. ``.env`` prefix check — catches ``.env``, ``.env.local``,
       ``.env.production``, etc. before the fnmatch loop.
    2. ``fnmatch.fnmatch(name, pattern)`` — covers exact names and glob patterns
       such as ``*.pem`` and ``*.key``.
    3. ``rel_path.startswith(prefix)`` — blocks writes inside protected directories
       such as ``.git/``, ``node_modules/``, etc.

    Args:
        rel_path: Relative path from the project root, with forward slashes.
                  Must NOT start with a separator or contain ``..``.

    Raises:
        ProtectedFileError: If the path matches any protected pattern.
    """
    name = Path(rel_path).name

    # Strategy 1: .env.* family (exact ".env" is also caught here)
    if name.startswith(".env"):
        raise ProtectedFileError(
            f"Modification of '{name}' is forbidden: .env files may contain secrets"
        )

    # Strategy 2: fnmatch against the filename
    for pattern in _PROTECTED_NAME_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            raise ProtectedFileError(
                f"Modification of '{name}' is forbidden (matches protected pattern '{pattern}')"
            )

    # Strategy 3: directory prefix check (normalise backslashes for Windows paths)
    norm = rel_path.replace("\\", "/")
    for prefix in _PROTECTED_DIR_PREFIXES:
        if norm.startswith(prefix):
            raise ProtectedFileError(
                f"Modification inside '{prefix.rstrip('/')}/' is forbidden"
            )


def _validate_write_target(abs_path: Path, project_root: Path) -> None:
    """
    Perform a full independent write-path security check on *abs_path*.

    This function is intentionally separate from ``ProjectScanner.safe_read``
    so that read-path and write-path security are independently maintained.

    Checks (applied in order — first failure raises immediately):
      1. Path must resolve strictly inside *project_root*.
      2. Relative path must not match any protected-file pattern.
      3. Target must not be a directory.
      4. Target must not have ``.git`` anywhere in its parts.
      5. Target must not be a symlink (prevents TOCTOU escape).

    Args:
        abs_path:     Resolved absolute path of the file to be written.
        project_root: Resolved absolute path of the project root.

    Raises:
        ValueError:         If the path escapes the root, is a directory, or
                            contains ``.git`` in its parts.
        ProtectedFileError: If the filename matches a protected pattern.
        ValueError:         If the target is a symlink.

    Note:
        This function is called at BOTH propose time (before the Groq call) and
        apply time (immediately before the disk write).  The second call catches
        any filesystem change (e.g. a symlink created between the two operations).
    """
    # 1. Must be strictly inside project root
    try:
        rel = abs_path.relative_to(project_root)
    except ValueError:
        raise ValueError(
            f"Write target escapes project root: '{abs_path}' is not under '{project_root}'"
        )

    # 2. Must not match protected patterns
    _check_protected(rel.as_posix())

    # 3. Must not be a directory
    if abs_path.is_dir():
        raise ValueError(f"Write target is a directory, not a file: '{abs_path}'")

    # 4. Must not be inside a .git directory
    if ".git" in abs_path.parts:
        raise ValueError(
            f"Modification of .git internals is forbidden: '{abs_path}'"
        )

    # 5. Must not be a symlink (TOCTOU protection)
    if abs_path.is_symlink():
        raise ValueError(
            f"Write target is a symlink; symlinks are not allowed as modification targets: "
            f"'{abs_path}'"
        )

    logger.debug("Write target validated: '%s'", abs_path)
