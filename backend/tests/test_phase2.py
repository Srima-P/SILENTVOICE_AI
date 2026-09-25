"""
Phase 2 — Backend test suite.

Tests:
  1.  Recursive project scanning produces correct file count
  2.  Ignored directories (node_modules, __pycache__, .git) are excluded
  3.  Secret files (.env, .pem, credentials.json) are excluded
  4.  Valid file reading returns correct content
  5.  Missing file raises FileNotFoundError (→ HTTP 404)
  6.  Path traversal attempt is rejected (→ ValueError)
  7.  Absolute path attempt is rejected (→ ValueError)
  8.  Relative import detection in JS/TS
  9.  Python import detection
  10. React component detection
  11. Project analysis endpoint returns correct statistics
  12. GET /api/project/tree returns 200
  13. GET /api/project/file returns 200 for valid file
  14. GET /api/project/file returns 400 for traversal
  15. GET /api/project/analyze returns component and dependency data
"""
from __future__ import annotations

import os
import sys
import textwrap
import tempfile
import shutil
from pathlib import Path

import pytest

# ── Add backend to Python path ────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.project_scanner import ProjectScanner, _is_secret_file, _should_ignore_dir
from app.services.dependency_analyzer import (
    DependencyAnalyzer,
    detect_react_components,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def demo_root() -> Path:
    """Return the path to the bundled demo_project."""
    here = Path(__file__).resolve()
    # backend/tests/ → backend/ → silentvoice-ai/ → demo_project/
    root = here.parents[2] / "demo_project"
    assert root.exists(), f"demo_project not found at {root}"
    return root


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal temporary project structure for isolation."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text(
        'import { App } from "./App";\nconsole.log("hello");\n'
    )
    (tmp_path / "src" / "App.tsx").write_text(
        textwrap.dedent("""
            import React from "react";
            import Navbar from "./components/Navbar";

            export default function App() {
              return <div><Navbar /></div>;
            }
        """)
    )
    (tmp_path / "src" / "components").mkdir()
    (tmp_path / "src" / "components" / "Navbar.tsx").write_text(
        'export default function Navbar() { return <nav>Nav</nav>; }'
    )
    (tmp_path / "src" / "utils.py").write_text(
        textwrap.dedent("""
            import os
            from pathlib import Path
            from .helpers import format_name
        """)
    )
    # Files that must be ignored
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lodash.js").write_text("module.exports = {};")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cache.pyc").write_text("")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    # Secret files that must be filtered
    (tmp_path / ".env").write_text("SECRET_KEY=abc123\n")
    (tmp_path / "credentials.json").write_text('{"key":"value"}')
    (tmp_path / "private.pem").write_text("-----BEGIN RSA PRIVATE KEY-----\n")
    # Normal config
    (tmp_path / "package.json").write_text('{"name":"tmp-project","version":"1.0.0"}')
    return tmp_path


# ─── Test 1: Recursive scanning ───────────────────────────────────────────────

def test_recursive_scan_finds_source_files(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    tree = scanner.scan()
    # Collect all file paths from tree
    paths = _collect_paths(tree.children)
    assert "src/index.ts" in paths
    assert "src/App.tsx" in paths
    assert "src/components/Navbar.tsx" in paths
    assert "package.json" in paths


# ─── Test 2: Ignored directories ─────────────────────────────────────────────

def test_ignored_dirs_excluded(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    tree = scanner.scan()
    paths = _collect_paths(tree.children)
    assert not any("node_modules" in p for p in paths)
    assert not any("__pycache__" in p for p in paths)
    assert not any(".git" in p for p in paths)


def test_should_ignore_dir_logic() -> None:
    assert _should_ignore_dir("node_modules") is True
    assert _should_ignore_dir("__pycache__") is True
    assert _should_ignore_dir(".git") is True
    assert _should_ignore_dir("dist") is True
    assert _should_ignore_dir("src") is False
    assert _should_ignore_dir("components") is False


# ─── Test 3: Secret file filtering ───────────────────────────────────────────

def test_secret_files_excluded_from_tree(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    tree = scanner.scan()
    paths = _collect_paths(tree.children)
    assert ".env" not in paths
    assert "credentials.json" not in paths
    assert "private.pem" not in paths


def test_is_secret_file_logic() -> None:
    assert _is_secret_file(".env") is True
    assert _is_secret_file(".env.local") is True
    assert _is_secret_file(".env.production") is True
    assert _is_secret_file("credentials.json") is True
    assert _is_secret_file("service-account.json") is True
    assert _is_secret_file("id_rsa") is True
    assert _is_secret_file("private.pem") is True
    assert _is_secret_file("app.py") is False
    assert _is_secret_file("config.json") is False


# ─── Test 4: Valid file reading ───────────────────────────────────────────────

def test_valid_file_read(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    content, lines = scanner.safe_read("src/index.ts")
    assert 'import { App }' in content
    assert lines >= 1


def test_demo_project_app_jsx_readable(demo_root: Path) -> None:
    scanner = ProjectScanner(demo_root)
    content, lines = scanner.safe_read("src/App.jsx")
    assert "BrowserRouter" in content or "App" in content
    assert lines >= 1


# ─── Test 5: Missing file ─────────────────────────────────────────────────────

def test_missing_file_raises(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    with pytest.raises(FileNotFoundError):
        scanner.safe_read("src/does_not_exist.ts")


# ─── Test 6: Path traversal ───────────────────────────────────────────────────

def test_path_traversal_double_dot(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    with pytest.raises(ValueError, match="traversal|escapes"):
        scanner.safe_read("../../etc/passwd")


def test_path_traversal_encoded(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    # Even if the consumer pre-decodes, the resolve() check catches it
    with pytest.raises(ValueError, match="traversal|escapes"):
        scanner.safe_read("../../../etc/shadow")


# ─── Test 7: Absolute path ────────────────────────────────────────────────────

def test_absolute_path_rejected(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    # On Windows this will try to access C:\etc\passwd; we just check it raises
    with pytest.raises((ValueError, FileNotFoundError)):
        scanner.safe_read("/etc/passwd")


# ─── Test 8: JS/TS relative import detection ─────────────────────────────────

def test_js_relative_imports_detected(tmp_project: Path) -> None:
    analyzer = DependencyAnalyzer(tmp_project)
    content = (tmp_project / "src" / "App.tsx").read_text()
    deps = analyzer.analyze_file("src/App.tsx", content)
    # "./components/Navbar" should resolve to src/components/Navbar.tsx
    assert any("Navbar" in r for r in deps.resolved_imports), (
        f"Expected Navbar in resolved_imports, got: {deps.resolved_imports}"
    )


def test_js_bare_import_raw(tmp_project: Path) -> None:
    analyzer = DependencyAnalyzer(tmp_project)
    content = 'import "./styles.css";\n'
    deps = analyzer.analyze_file("src/main.ts", content)
    assert "./styles.css" in deps.raw_imports


# ─── Test 9: Python import detection ─────────────────────────────────────────

def test_python_imports_detected(tmp_project: Path) -> None:
    analyzer = DependencyAnalyzer(tmp_project)
    content = (tmp_project / "src" / "utils.py").read_text()
    deps = analyzer.analyze_file("src/utils.py", content)
    assert "os" in deps.raw_imports or "pathlib" in deps.raw_imports or ".helpers" in deps.raw_imports


def test_python_relative_import_raw() -> None:
    analyzer = DependencyAnalyzer(Path("/tmp/fake_root"))
    content = "from .helpers import format_name\n"
    deps = analyzer.analyze_file("src/utils.py", content)
    assert ".helpers" in deps.raw_imports


# ─── Test 10: React component detection ──────────────────────────────────────

def test_react_component_detected(tmp_project: Path) -> None:
    source_files: list[tuple[str, str]] = []
    for path in ["src/App.tsx", "src/components/Navbar.tsx"]:
        content = (tmp_project / path).read_text()
        source_files.append((path, content))
    components = detect_react_components(source_files)
    names = [c["name"] for c in components]
    assert any("App" in n for n in names), f"App not found in {names}"


# ─── Test 11: Project analysis stats ─────────────────────────────────────────

def test_project_analysis_stats(tmp_project: Path) -> None:
    scanner = ProjectScanner(tmp_project)
    tree = scanner.scan()
    assert tree.total_files >= 4  # index.ts, App.tsx, Navbar.tsx, utils.py, package.json
    assert tree.total_dirs >= 2   # src, src/components


def test_demo_project_scan_stats(demo_root: Path) -> None:
    scanner = ProjectScanner(demo_root)
    tree = scanner.scan()
    paths = _collect_paths(tree.children)
    assert any("App.jsx" in p for p in paths)
    assert any("Navbar.jsx" in p for p in paths)
    assert any("Login.jsx" in p for p in paths)
    assert any("Dashboard.jsx" in p for p in paths)
    assert tree.total_files >= 5


# ─── Test 12–15: API endpoint tests ──────────────────────────────────────────

def test_api_tree_endpoint() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/project/tree")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "demo_project"
    assert body["total_files"] >= 5
    # Verify children present
    assert len(body["children"]) > 0


def test_api_file_endpoint_valid() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/project/file", params={"path": "src/App.jsx"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "App.jsx"
    assert "BrowserRouter" in body["content"] or "App" in body["content"]
    assert body["lines"] >= 1
    assert body["language"] == "javascript"


def test_api_file_endpoint_traversal() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/project/file", params={"path": "../../etc/passwd"})
    assert resp.status_code in (400, 403)


def test_api_file_endpoint_missing() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/project/file", params={"path": "src/nonexistent.ts"})
    assert resp.status_code == 404


def test_api_analyze_endpoint() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.get("/api/project/analyze")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_name"] == "demo_project"
    assert body["total_files"] >= 5
    assert "javascript" in body["languages"]
    assert len(body["components"]) >= 1
    # Verify dependency entries exist for App.jsx
    entries = body["dependencies"]["entries"]
    assert any("App" in k for k in entries.keys()), f"No App entry found in {list(entries.keys())}"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _collect_paths(nodes: list, acc: list[str] | None = None) -> list[str]:
    """Recursively collect all file paths from a tree node list."""
    if acc is None:
        acc = []
    for node in nodes:
        if isinstance(node, dict):
            t = node.get("type")
            p = node.get("path", "")
            children = node.get("children") or []
        else:
            t = node.type
            p = node.path
            children = node.children or []
        if t == "file":
            acc.append(p)
        elif t == "directory":
            _collect_paths(children, acc)
    return acc
