"""
GroqService — Phase 3 AI integration.

Responsibilities:
  • Load API key safely from environment (never from request)
  • Manage chat completions via Groq's REST API
  • Enforce token / size limits
  • Handle API errors, timeouts, and rate-limits gracefully
  • Never surface raw stack traces or key material to callers

The service uses httpx for async HTTP so it fits cleanly inside FastAPI's
async request handlers.  The groq Python SDK is also acceptable, but plain
HTTP keeps the dependency surface minimal.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger("silentvoice.groq")

# Groq Chat Completions endpoint
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Hard cap: never send more than 80 000 chars in a single prompt (~20 K tokens).
# The per-file soft cap is controlled by settings.max_file_size_for_ai.
_PROMPT_CHAR_LIMIT = 80_000

# Request timeout in seconds
_TIMEOUT = 60.0


class GroqError(Exception):
    """Raised when the Groq API returns an error or is unavailable."""


class GroqService:
    """
    Thin wrapper around the Groq Chat Completions REST API.

    Usage:
        svc = GroqService()
        text = await svc.complete(system_prompt, user_prompt)
    """

    def __init__(self) -> None:
        self._key: str = settings.groq_api_key
        self._model: str = settings.groq_model

    # ── Public API ─────────────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        """Return True if a non-empty API key is set."""
        return bool(self._key and self._key.strip())

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """
        Send a two-message (system + user) chat completion request to Groq.

        Returns the assistant's response text.
        Raises GroqError on any failure (key missing, network, API error, timeout).
        """
        if not self.is_configured():
            raise GroqError(
                "GROQ_API_KEY is not set. Add your key to the .env file to enable AI features."
            )

        # Truncate prompts that exceed the hard cap
        combined = system_prompt + user_prompt
        if len(combined) > _PROMPT_CHAR_LIMIT:
            # Shorten the user prompt (system prompt is small by design)
            overage = len(combined) - _PROMPT_CHAR_LIMIT
            user_prompt = user_prompt[: len(user_prompt) - overage] + "\n\n[... content truncated for token safety ...]"
            logger.warning("Prompt truncated: removed %d chars", overage)

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(GROQ_API_URL, json=payload, headers=headers)

                print("MODEL SENT:", self._model)
                print("STATUS:", response.status_code)
                print("BODY:", response.text)
        except httpx.TimeoutException:
            raise GroqError("Groq request timed out. Please try again.")
        except httpx.RequestError as exc:
            raise GroqError(f"Network error contacting Groq: {exc}") from exc

        if response.status_code == 401:
            raise GroqError("Invalid GROQ_API_KEY. Check your .env file.")
        if response.status_code == 429:
            raise GroqError("Groq rate limit reached. Please wait a moment and try again.")
        if response.status_code >= 500:
            raise GroqError(f"Groq service error (HTTP {response.status_code}). Try again shortly.")
        if not response.is_success:
            try:
                detail = response.json().get("error", {}).get("message", response.text[:200])
            except Exception:
                detail = response.text[:200]
            raise GroqError(f"Groq API error (HTTP {response.status_code}): {detail}")

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise GroqError(f"Unexpected response format from Groq: {exc}") from exc

    # ── Convenience: structured prompts ───────────────────────────────────────

    async def explain_file(
        self,
        file_path: str,
        language: str,
        content: str,
        dependencies: list[str],
    ) -> str:
        """Generate a structured explanation for a source file."""
        deps_text = "\n".join(f"  - {d}" for d in dependencies) if dependencies else "  (none detected)"
        system = (
            "You are an experienced software engineering mentor reviewing code for a colleague. "
            "Be clear, concise, and use plain English. Format your response in Markdown."
        )
        user = f"""Explain this source file: `{file_path}`

**Language:** {language}
**Known dependencies (imports that resolve to project files):**
{deps_text}

**Source code:**
```{language}
{content}
```

Provide a structured explanation with these sections:

## Purpose
One paragraph describing what this file does and why it exists.

## Main Responsibilities
Bullet list of primary responsibilities.

## Key Functions / Components
Brief description of the most important functions, classes, or components.

## State Management
Describe how state is managed (if applicable). Say "Not applicable" if this file has no state.

## Dependencies
What other parts of the project does this file depend on, and why?

## Data Flow
Briefly trace the primary data flow through this file.

## Potential Improvements
1–3 concrete, actionable suggestions (keep them brief).
"""
        return await self.complete(system, user)

    async def summarize_file(
        self,
        file_path: str,
        language: str,
        content: str,
    ) -> str:
        """Generate a concise summary for a source file."""
        system = (
            "You are a senior software engineer writing a brief technical summary "
            "for a code review. Be precise and concise. Use Markdown."
        )
        user = f"""Summarize this source file in 3–5 sentences: `{file_path}`

**Language:** {language}

```{language}
{content}
```

Then list the 3 most important things a developer needs to know about this file as bullet points.
"""
        return await self.complete(system, user, max_tokens=800)

    async def explain_dependencies(
        self,
        file_path: str,
        resolved_deps: list[str],
        unresolved_deps: list[str],
        file_content: str,
        language: str,
    ) -> str:
        """Explain the dependency graph for a file."""
        system = (
            "You are a software architect explaining project structure to a developer. "
            "Use Markdown."
        )
        resolved_text = "\n".join(f"  - {d}" for d in resolved_deps) if resolved_deps else "  (none)"
        unresolved_text = "\n".join(f"  - {d}" for d in unresolved_deps) if unresolved_deps else "  (none)"
        user = f"""Explain the dependencies of `{file_path}` ({language}).

**Resolved project imports (files that exist in the project):**
{resolved_text}

**External / unresolved imports:**
{unresolved_text}

**File source (for context):**
```{language}
{file_content}
```

Provide:

## Direct Dependencies
Explain each resolved project dependency and its role.

## External Dependencies
List and briefly explain external packages imported.

## Dependency Role in Project
How does this file fit into the larger dependency graph?

## Observations
Any notable patterns, potential circular dependencies, or coupling concerns?
"""
        return await self.complete(system, user)

    async def project_overview(
        self,
        project_name: str,
        total_files: int,
        source_files: int,
        languages: dict[str, int],
        components: list[str],
        dependency_entries: dict[str, list[str]],
    ) -> str:
        """Generate a project-level overview without sending all source code."""
        system = (
            "You are a principal engineer providing a high-level technical overview "
            "of a codebase to a new team member. Be concise, clear, and helpful. Use Markdown."
        )
        lang_lines = "\n".join(f"  - {lang}: {count} file(s)" for lang, count in sorted(languages.items(), key=lambda x: -x[1]))
        comp_lines = "\n".join(f"  - {c}" for c in components[:20])
        dep_lines = "\n".join(
            f"  - `{src}` → {', '.join(f'`{d}`' for d in deps[:3])}{'…' if len(deps) > 3 else ''}"
            for src, deps in list(dependency_entries.items())[:15]
        )
        user = f"""Give a technical overview of this project.

**Project name:** {project_name}
**Total files:** {total_files}
**Source files analyzed:** {source_files}

**Language breakdown:**
{lang_lines}

**Detected components / modules:**
{comp_lines if components else "  (none detected)"}

**Key dependency relationships (sample):**
{dep_lines if dependency_entries else "  (no dependency data)"}

Provide:

## Project Overview
What kind of project is this? What is its likely purpose?

## Architecture
Describe the apparent architecture pattern (e.g., component-based React app, REST API, etc.).

## Technology Stack
List and briefly describe the detected technologies.

## Key Components
Describe the most important detected components and their roles.

## Project Structure Observations
Notable observations about how the project is organized.

## Recommendations
1–3 high-level recommendations for maintainability or improvement.
"""
        return await self.complete(system, user, max_tokens=1200)


    async def find_dependents(
        self,
        file_path: str,
        dependents: list[str],
        language: str,
    ) -> str:
        """Generate a prose explanation of which files depend on the given file."""
        system = (
            "You are a software architect explaining project structure to a developer. "
            "Use Markdown. Be concise and precise."
        )
        dep_lines = "\n".join(f"  - {d}" for d in dependents) if dependents else "  (none detected)"
        user = f"""Which files depend on `{file_path}` ({language})?

**Files that import or depend on `{file_path}`:**
{dep_lines}

Provide:

## Files That Depend On `{file_path}`
List each dependent file and briefly explain why it might depend on this module.

## Impact Analysis
What would break or need updating if `{file_path}` were changed?

## Observations
Any notable patterns (e.g., widely used utility, single entry point, etc.)?
"""
        return await self.complete(system, user, max_tokens=800)

    async def explain_relationship(
        self,
        file_a: str,
        file_b: str,
        language: str,
        content_a: str,
        content_b: str,
        deps_a: list[str],
        deps_b: list[str],
    ) -> str:
        """Explain how two files relate and interact with each other."""
        system = (
            "You are a software architect explaining how two modules relate to a developer. "
            "Use Markdown. Be clear and specific."
        )
        user = f"""Explain the relationship between `{file_a}` and `{file_b}` ({language}).

**`{file_a}` dependencies (project files it imports):** {', '.join(deps_a) if deps_a else 'none'}
**`{file_b}` dependencies (project files it imports):** {', '.join(deps_b) if deps_b else 'none'}

**Source of `{file_a}`:**
```{language}
{content_a[:3000]}{'...[truncated]' if len(content_a) > 3000 else ''}
```

**Source of `{file_b}`:**
```{language}
{content_b[:3000]}{'...[truncated]' if len(content_b) > 3000 else ''}
```

Provide:

## Relationship Summary
One paragraph: how do these files relate to each other?

## Data Flow
How does data or control flow between them?

## Direct Dependencies
Does either file directly import the other? Explain the direction.

## Shared Concerns
Do they share state, types, utilities, or context?

## Coupling Assessment
Are they tightly or loosely coupled? Is this appropriate?
"""
        return await self.complete(system, user, max_tokens=1000)

    async def show_related(
        self,
        file_path: str,
        language: str,
        forward_deps: list[str],
        reverse_deps: list[str],
    ) -> str:
        """Summarise the neighbourhood of files related to the given file."""
        system = (
            "You are a software architect giving a developer a map of related code. "
            "Use Markdown. Be concise."
        )
        fwd = "\n".join(f"  - {d}" for d in forward_deps) if forward_deps else "  (none)"
        rev = "\n".join(f"  - {d}" for d in reverse_deps) if reverse_deps else "  (none)"
        user = f"""Show the related files for `{file_path}` ({language}).

**Files `{file_path}` imports (forward dependencies):**
{fwd}

**Files that import `{file_path}` (reverse dependencies):**
{rev}

Provide:

## Files `{file_path}` Depends On
Brief description of each import and why it's needed.

## Files That Depend On `{file_path}`
Brief description of each file that uses this module.

## Role in the Project
Based on the above, what role does `{file_path}` play in the overall architecture?
"""
        return await self.complete(system, user, max_tokens=800)


    # ── Phase 5: Onboarding prompts ───────────────────────────────────────────

    async def onboarding_start(
        self,
        project_name: str,
        total_files: int,
        languages: dict[str, int],
        components: list[str],
        dep_sample: dict[str, list[str]],
        setup_hint: str,
    ) -> str:
        """Generate a comprehensive onboarding overview for a new developer."""
        system = (
            "You are an expert software engineer onboarding a new developer to an unfamiliar repository. "
            "Be helpful, clear, and grounded in the evidence provided. "
            "Clearly distinguish detected facts from reasonable inferences. "
            "Do NOT invent technologies, files, or functionality not supported by the data. "
            "Use Markdown with clear section headings."
        )
        lang_lines = "\n".join(f"  - {k}: {v} file(s)" for k, v in sorted(languages.items(), key=lambda x: -x[1]))
        comp_lines = "\n".join(f"  - {c}" for c in components[:15]) or "  (none detected)"
        dep_lines = "\n".join(
            f"  - `{src}` → {', '.join(f'`{d}`' for d in deps[:3])}"
            for src, deps in list(dep_sample.items())[:8]
        ) or "  (no dependency data)"

        user = f"""A new developer just joined the team and needs to understand this repository.

**Project name:** {project_name}
**Total files:** {total_files}
**Technology hint:** {setup_hint or "unknown"}
**Language breakdown:**
{lang_lines or "  (no language data)"}
**Detected components/modules:**
{comp_lines}
**Sample dependency relationships:**
{dep_lines}

Generate a complete developer onboarding guide with these exact sections:

## What This Project Is
A high-level description of the project's apparent purpose, based on the evidence above.

## Technology Stack
The detected technologies, languages, and frameworks.

## Project Structure
Important files and directories a developer should know about.

## Architecture
The apparent architectural pattern (e.g., component-based React SPA, REST API, etc.).

## Important Components
The key components/modules and what each one does.

## How the Project Fits Together
Explain the major dependency relationships in plain English.

## Where Should I Start?
Suggest a logical starting point — which file(s) to read first and why.

Distinguish clearly between what was detected vs. what is inferred.
Do NOT invent file names, libraries, or patterns not supported by the data.
"""
        return await self.complete(system, user, max_tokens=1400)

    async def architecture_overview(
        self,
        project_name: str,
        languages: dict[str, int],
        components: list[str],
        dep_sample: dict[str, list[str]],
        total_files: int,
    ) -> str:
        """Explain the apparent project architecture."""
        system = (
            "You are a software architect explaining how a project is structured to a developer. "
            "Be precise and grounded in the provided data. Use Markdown."
        )
        lang_lines = "\n".join(f"  - {k}: {v} file(s)" for k, v in sorted(languages.items(), key=lambda x: -x[1]))
        comp_lines = "\n".join(f"  - {c}" for c in components[:15]) or "  (none detected)"
        dep_lines = "\n".join(
            f"  - `{src}` → {', '.join(f'`{d}`' for d in deps[:3])}"
            for src, deps in list(dep_sample.items())[:10]
        ) or "  (no dependency data)"
        user = f"""Explain the architecture of `{project_name}`.

**Files:** {total_files}
**Languages:**
{lang_lines or "  (no data)"}
**Detected components:**
{comp_lines}
**Dependency relationships (sample):**
{dep_lines}

Provide:

## Architectural Pattern
What is the overall architectural style? (e.g., MVC, component-based, microservices, monolith)

## Layer Breakdown
Describe the logical layers (e.g., UI, API, data, utilities).

## Data Flow
How does data flow through the system from input to output?

## Module Responsibilities
What does each detected component/module own?

## Coupling and Cohesion
Are components loosely or tightly coupled? Any notable patterns?

Only describe what the data supports. Do not invent technologies.
"""
        return await self.complete(system, user, max_tokens=1000)

    async def setup_guidance(
        self,
        project_name: str,
        languages: dict[str, int],
        setup_contents: dict[str, str],
    ) -> str:
        """Generate setup guidance from actual project setup files."""
        system = (
            "You are a senior developer writing a clear setup guide for a new team member. "
            "Use only the provided file content — do not invent commands or steps. "
            "If a file is not present, say so. Use Markdown."
        )
        files_text = ""
        for fname, content in setup_contents.items():
            files_text += f"\n\n### `{fname}`\n```\n{content}\n```"

        if not files_text:
            files_text = "\n\n*(No setup files were found in the project root.)*"

        lang_list = ", ".join(sorted(languages.keys())) or "unknown"
        user = f"""Generate setup guidance for `{project_name}`.

**Detected languages:** {lang_list}
**Available setup files:**{files_text}

Provide:

## Prerequisites
List what needs to be installed first, based on the detected language/files.

## Installation Steps
Step-by-step instructions derived directly from the files above.
If no setup files are available, provide general guidance for the detected language stack.

## Running the Project
How to start the development server or run the application, based on available scripts.

## Environment Configuration
Any environment variables or config files that need to be set up.

## Common Pitfalls
Any obvious setup issues based on the project structure.

Base every step on what the files actually say. Do not make up commands.
"""
        return await self.complete(system, user, max_tokens=1000)

    async def beginner_tasks(
        self,
        project_name: str,
        languages: dict[str, int],
        components: list[str],
        dep_sample: dict[str, list[str]],
    ) -> str:
        """Suggest beginner tasks grounded in actual project files."""
        system = (
            "You are an engineering mentor creating a learning plan for a junior developer. "
            "Every task MUST reference a real component or file from the data provided. "
            "Do NOT invent files or components. Use Markdown."
        )
        comp_lines = "\n".join(f"  - {c}" for c in components[:15]) or "  (none detected)"
        lang_list = ", ".join(sorted(languages.keys())) or "unknown"
        dep_lines = "\n".join(
            f"  - `{src}` → {', '.join(f'`{d}`' for d in deps[:3])}"
            for src, deps in list(dep_sample.items())[:8]
        ) or "  (no data)"
        user = f"""Create beginner learning tasks for `{project_name}`.

**Language(s):** {lang_list}
**Detected components (use ONLY these):**
{comp_lines}
**Dependency relationships:**
{dep_lines}

Generate 5–7 beginner-friendly tasks. For each task provide:

### Task N: [Title]
- **Target:** The specific file or component from the list above
- **Goal:** What the developer will understand after completing this task
- **Steps:** 2–4 concrete exploration steps (read, trace, annotate)
- **Difficulty:** Beginner

Only reference components and files that appear in the detected list above.
Do NOT invent fictional file names.
"""
        return await self.complete(system, user, max_tokens=1200)


# ── Module-level singleton (re-created each request so key changes are picked up) ──
def get_groq_service() -> GroqService:
    return GroqService()

