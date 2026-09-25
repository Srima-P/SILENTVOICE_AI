"""
ConversationManager — Phase 4 context resolution service.

Centralises the logic for determining the "active file" for a given request.
Stateless: all inputs are passed as arguments — easy to test and future-proof
for Phase 5 voice integration.

Priority order for resolving the active file:
  1. Explicit file reference extracted from the user's current message.
  2. Currently selected file in the Project Explorer (frontend passes this).
  3. Last file mentioned in the recent conversation history.
  4. No file context available.

Usage:
    from app.services.conversation_manager import ConversationManager

    manager = ConversationManager(tree_nodes)
    ctx = manager.resolve_context(
        message="What are its dependencies?",
        selected_file="src/components/Login.jsx",
        conversation_history=[...],
    )
    # ctx.resolved_file → "src/components/Login.jsx"
    # ctx.context_source → "selected"
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.schemas.assistant import ConversationTurn
from app.services.file_resolver import FileResolver

logger = logging.getLogger("silentvoice.conversation_manager")

# Reuse the same file-reference pattern as intent_classifier.py
_FILE_REF_PATTERN = re.compile(
    r"\b([\w\-./]+\.(?:py|js|jsx|ts|tsx|html|css|json|md|yaml|yml|sh|go|rs"
    r"|java|kt|rb|php|c|cpp|h|hpp|cs|vue|svelte|toml|sql))\b",
    re.IGNORECASE,
)

# Pronouns / phrases that signal the user is referring back to a previous file
_REFERBACK_PATTERN = re.compile(
    r"\b(it|this|that|its|the\s+file|this\s+file|that\s+file|the\s+component|"
    r"this\s+component|the\s+module|this\s+module)\b",
    re.IGNORECASE,
)


@dataclass
class ContextResolution:
    """Result of resolving the active file context for a request."""
    resolved_file: Optional[str] = None
    context_source: str = "none"   # explicit | selected | memory | none
    candidates: list[str] = field(default_factory=list)


class ConversationManager:
    """
    Resolves the active file for a conversational turn.

    Args:
        tree_nodes: The project file tree (list of raw node dicts or FileNode objects).
                    May be empty or None — all paths gracefully degrade.
    """

    def __init__(self, tree_nodes: list | None = None) -> None:
        self._resolver: Optional[FileResolver] = None
        if tree_nodes:
            try:
                self._resolver = FileResolver(tree_nodes)
            except Exception as exc:
                logger.warning("ConversationManager: could not build FileResolver: %s", exc)

    # ── Public API ─────────────────────────────────────────────────────────────

    def resolve_context(
        self,
        message: str,
        selected_file: Optional[str],
        conversation_history: list[ConversationTurn],
    ) -> ContextResolution:
        """
        Resolve the active file context for the given request.

        Priority:
          1. Explicit file ref in `message`
          2. `selected_file` (from Project Explorer)
          3. Last file mentioned in `conversation_history`
          4. No context
        """
        # 1. Explicit file reference in the current message
        explicit_ref = _extract_file_reference(message)
        if explicit_ref and self._resolver:
            result = self._resolver.resolve(explicit_ref)
            if result.found:
                logger.debug("Context resolved from explicit ref: %s", result.path)
                return ContextResolution(
                    resolved_file=result.path,
                    context_source="explicit",
                )
            if result.candidates:
                # Ambiguous — surface candidates to the route handler
                return ContextResolution(
                    resolved_file=None,
                    context_source="explicit",
                    candidates=result.candidates,
                )
            # Explicit ref present but not resolvable — do not fall through to
            # selected/memory; the user named a specific file that doesn't exist.
            return ContextResolution(context_source="explicit")

        # If there's an explicit file ref but no resolver, still record intent
        if explicit_ref:
            return ContextResolution(
                resolved_file=explicit_ref,
                context_source="explicit",
            )

        # 2. Selected file from Project Explorer
        if selected_file and selected_file.strip():
            logger.debug("Context resolved from selected_file: %s", selected_file)
            return ContextResolution(
                resolved_file=selected_file.strip(),
                context_source="selected",
            )

        # 3. Conversation memory — only activate if the message contains a
        #    referback pronoun (otherwise an unrelated question would inherit context)
        if conversation_history and _has_referback(message):
            last_file = _extract_last_mentioned_file(conversation_history)
            if last_file:
                logger.debug("Context resolved from conversation memory: %s", last_file)
                return ContextResolution(
                    resolved_file=last_file,
                    context_source="memory",
                )

        return ContextResolution(context_source="none")

    def extract_second_file(self, message: str) -> Optional[str]:
        """
        Extract the second file reference from a relationship query like
        'How does Login.jsx connect to App.jsx?'

        Returns the second match, or None.
        """
        matches = _FILE_REF_PATTERN.findall(message)
        return matches[1] if len(matches) >= 2 else None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_file_reference(text: str) -> Optional[str]:
    """Return the first file-like reference found in the text, or None."""
    m = _FILE_REF_PATTERN.search(text)
    return m.group(1) if m else None


def _has_referback(message: str) -> bool:
    """Return True if the message contains a pronoun/phrase referring to a prior file."""
    return bool(_REFERBACK_PATTERN.search(message))


def _extract_last_mentioned_file(history: list[ConversationTurn]) -> Optional[str]:
    """
    Walk the conversation history in reverse (most recent first) and return
    the first file path found in an assistant message.

    Assistant messages may contain:
      - The resolved file path inline in the text
      - Markdown code references like `src/components/Login.jsx`
    """
    for turn in reversed(history):
        if turn.role != "assistant":
            continue
        m = _FILE_REF_PATTERN.search(turn.content)
        if m:
            return m.group(1)
    return None
