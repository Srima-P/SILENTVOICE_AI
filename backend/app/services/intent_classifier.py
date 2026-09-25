"""
IntentClassifier — deterministic, pattern-based intent detection.

No LLM is used here — reliability over flexibility.

Supported intents (Phase 3):
  explain_file          Explain what a specific file does
  summarize_file        Give a brief summary of a file
  explain_dependencies  Explain the imports/dependencies of a file
  project_overview      Give a high-level overview of the whole project

Phase 4 additions:
  find_dependents       Which files depend on / import a given file
  explain_relationship  How two specific files relate / interact
  show_related          Show files related to the current file

Detection strategy:
  1. Keyword matching against normalised input
  2. File-reference detection (*.ext patterns, known filenames)
  3. Fall back to "unsupported" with a helpful message

Note: Follow-up phrases with no explicit file reference (e.g. "summarize it",
      "what are its dependencies?") are intentionally classified to the matching
      intent with file_reference=None. The ConversationManager resolves the
      active file from context (selected file / conversation memory).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    EXPLAIN_FILE = "explain_file"
    SUMMARIZE_FILE = "summarize_file"
    EXPLAIN_DEPENDENCIES = "explain_dependencies"
    PROJECT_OVERVIEW = "project_overview"
    # Phase 4
    FIND_DEPENDENTS = "find_dependents"
    EXPLAIN_RELATIONSHIP = "explain_relationship"
    SHOW_RELATED = "show_related"
    UNSUPPORTED = "unsupported"


# Supported source-file extensions (lowercase)
_CODE_EXTENSIONS = frozenset(
    ".py .js .jsx .ts .tsx .html .css .json .md .yaml .yml .sh .go .rs "
    ".java .kt .rb .php .c .cpp .h .hpp .cs .vue .svelte .toml .ini .sql".split()
)

# Pattern to detect file-like references: word.ext or path/to/file.ext
_FILE_REF_PATTERN = re.compile(
    r"\b([\w\-./]+\.(?:py|js|jsx|ts|tsx|html|css|json|md|yaml|yml|sh|go|rs|java|kt|rb|php|c|cpp|h|hpp|cs|vue|svelte|toml|sql))\b",
    re.IGNORECASE,
)


@dataclass
class ClassificationResult:
    intent: Intent
    file_reference: Optional[str] = None    # raw file mention from user input
    confidence: float = 1.0                 # 0–1, for diagnostics
    explanation: str = ""                   # human-readable reasoning

    @property
    def is_file_intent(self) -> bool:
        return self.intent in (
            Intent.EXPLAIN_FILE,
            Intent.SUMMARIZE_FILE,
            Intent.EXPLAIN_DEPENDENCIES,
            # Phase 4
            Intent.FIND_DEPENDENTS,
            Intent.EXPLAIN_RELATIONSHIP,
            Intent.SHOW_RELATED,
        )


# ─── Keyword tables ───────────────────────────────────────────────────────────

# (pattern_regex, intent_to_assign)
# Ordered: more specific patterns first
_INTENT_PATTERNS: list[tuple[re.Pattern[str], Intent]] = [
    # ── Phase 4: Find dependents — "which files depend on X", "who imports X" ──
    (re.compile(
        r"\b("
        r"which\s+files?\s+(depend|import|use|require)\s*(on\s*)?"
        r"|who\s+(imports?|uses?|depends?\s+on|requires?)\s"
        r"|what\s+(imports?|uses?|depends?\s+on|requires?)\s"
        r"|files?\s+that\s+(import|depend|use|require)"
        r"|dependents?\s*(of|for|on)?"
        r"|reverse\s+dep"
        r")\b",
        re.I,
    ), Intent.FIND_DEPENDENTS),

    # ── Phase 4: Explain relationship between two files ──────────────────────
    (re.compile(
        r"\b("
        r"how\s+does\s+\S+\s+(connect|relate|interact|link|work\s+with)"
        r"|relationship\s+between"
        r"|how\s+(do|does|are)\s+.*(connect|relate|interact|linked|related)"
        r"|explain\s+(the\s+)?(relationship|connection|interaction)\s+between"
        r"|how\s+.*(talk|communicate|interface)\s+(to|with)"
        r")\b",
        re.I,
    ), Intent.EXPLAIN_RELATIONSHIP),

    # ── Phase 4: Show related files ──────────────────────────────────────────
    (re.compile(
        r"\b("
        r"show\s+(me\s+)?(related|similar|connected|linked|associated)"
        r"|related\s+(files?|components?|modules?)"
        r"|what\s+(else\s+)?(is\s+)?(related|connected|linked|associated)"
        r"|find\s+related"
        r")\b",
        re.I,
    ), Intent.SHOW_RELATED),

    # ── Project-level overview — must come before generic explain ─────────────
    (re.compile(
        r"\b(project\s*(overview|summary|analysis|structure|breakdown)"
        r"|overview\s*of\s*(the\s*)?project"
        r"|analyze\s*(the\s*)?project"
        r"|what\s*(does|is)\s*(this|the)\s*project"
        r"|describe\s*(the\s*)?project)\b",
        re.I,
    ), Intent.PROJECT_OVERVIEW),

    # ── Dependency explanation — "import" / "depend" / "dependencies" ─────────
    (re.compile(
        r"\b("
        r"explain\s*(the\s*)?(imports?|dependencies|deps)\s*(of|for|in)?"
        r"|what\s*(does|do|is|are|will|did)\s+\S+\s*(import|depend|require)"
        r"|\S+\s+(imports?|depends?\s+on|requires?)"
        r"|dependencies?\s*(of|for|in)"
        r"|show\s*(me\s*)?(the\s*)?(imports?|dependencies|deps)"
        r"|what\s+(does\s+it|are\s+its?)\s*(import|depend|require|dependencies|deps)"
        r"|its?\s+dependencies"
        r")\b",
        re.I,
    ), Intent.EXPLAIN_DEPENDENCIES),

    # ── Summarize — "simply" treated as summarize ─────────────────────────────
    (re.compile(
        r"\b(summar(ize|ise|y)|brief|briefly|tldr|tl;dr"
        r"|quick\s*(overview|summary)"
        r"|in\s*a\s*few\s*words"
        r"|short\s*(description|summary)"
        r"|simply|explain\s+(it\s+)?simply|simple\s+explanation"
        r")\b",
        re.I,
    ), Intent.SUMMARIZE_FILE),

    # ── Explain / describe / what does ───────────────────────────────────────
    (re.compile(
        r"\b(explain|describe"
        r"|what\s*(does|is|are)\s*(this\s*file\s*do|it\s*do)?"
        r"|how\s*does\s*(it|this)\s*work"
        r"|tell\s*me\s*(about|what)"
        r"|walk\s*me\s*through"
        r"|show\s*me"
        r"|review"
        r")\b",
        re.I,
    ), Intent.EXPLAIN_FILE),
]


def _extract_file_reference(text: str) -> Optional[str]:
    """Return the first file-like reference found in the text, or None."""
    m = _FILE_REF_PATTERN.search(text)
    return m.group(1) if m else None


def classify(text: str) -> ClassificationResult:
    """
    Classify the user's natural language request into a supported intent.

    >>> classify("Explain Login.jsx")
    ClassificationResult(intent=<Intent.EXPLAIN_FILE>, file_reference='Login.jsx', ...)

    >>> classify("What does App.jsx do?")
    ClassificationResult(intent=<Intent.EXPLAIN_FILE>, file_reference='App.jsx', ...)

    >>> classify("Summarize Dashboard.jsx")
    ClassificationResult(intent=<Intent.SUMMARIZE_FILE>, file_reference='Dashboard.jsx', ...)

    >>> classify("Explain dependencies of App.jsx")
    ClassificationResult(intent=<Intent.EXPLAIN_DEPENDENCIES>, file_reference='App.jsx', ...)

    >>> classify("Give me a project overview")
    ClassificationResult(intent=<Intent.PROJECT_OVERVIEW>, file_reference=None, ...)

    >>> classify("Which files depend on Login.jsx?")
    ClassificationResult(intent=<Intent.FIND_DEPENDENTS>, file_reference='Login.jsx', ...)

    >>> classify("How does Login.jsx connect to App.jsx?")
    ClassificationResult(intent=<Intent.EXPLAIN_RELATIONSHIP>, file_reference='Login.jsx', ...)

    >>> classify("Show related components")
    ClassificationResult(intent=<Intent.SHOW_RELATED>, file_reference=None, ...)

    >>> classify("Summarize it")
    ClassificationResult(intent=<Intent.SUMMARIZE_FILE>, file_reference=None, ...)

    >>> classify("What are its dependencies?")
    ClassificationResult(intent=<Intent.EXPLAIN_DEPENDENCIES>, file_reference=None, ...)
    """
    normalised = text.strip()
    file_ref = _extract_file_reference(normalised)

    # 1. Try intent pattern matching
    for pattern, intent in _INTENT_PATTERNS:
        if pattern.search(normalised):
            # Dependency intent without a file ref — allow it through (context will supply file)
            # FIND_DEPENDENTS without a file ref — fall through to avoid misclassification
            if intent == Intent.FIND_DEPENDENTS and not file_ref:
                continue
            return ClassificationResult(
                intent=intent,
                file_reference=file_ref,
                confidence=0.95,
                explanation=f"Matched pattern for '{intent.value}'",
            )

    # 2. If user just typed a filename with no verb, default to explain
    if file_ref and not any(p.search(normalised) for p, _ in _INTENT_PATTERNS):
        return ClassificationResult(
            intent=Intent.EXPLAIN_FILE,
            file_reference=file_ref,
            confidence=0.75,
            explanation="No explicit intent verb — defaulting to explain_file for bare filename.",
        )

    # 3. Unsupported
    return ClassificationResult(
        intent=Intent.UNSUPPORTED,
        file_reference=file_ref,
        confidence=0.0,
        explanation=(
            "Could not determine intent. "
            "Try: 'Explain Login.jsx', 'Summarize App.jsx', "
            "'Explain dependencies of App.jsx', 'Give me a project overview', "
            "'Which files depend on Login.jsx?', or 'Show related components'."
        ),
    )
