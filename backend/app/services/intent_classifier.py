"""
IntentClassifier — deterministic, pattern-based intent detection.

No LLM is used here — reliability over flexibility.

Supported intents:
  explain_file          Explain what a specific file does
  summarize_file        Give a brief summary of a file
  explain_dependencies  Explain the imports/dependencies of a file
  project_overview      Give a high-level overview of the whole project

Detection strategy:
  1. Keyword matching against normalised input
  2. File-reference detection (*.ext patterns, known filenames)
  3. Fall back to "unsupported" with a helpful message
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
        )


# ─── Keyword tables ───────────────────────────────────────────────────────────

# (pattern_regex, intent_to_assign)
# Ordered: more specific patterns first
_INTENT_PATTERNS: list[tuple[re.Pattern[str], Intent]] = [
    # Project-level overview — must come before generic explain
    (re.compile(r"\b(project\s*(overview|summary|analysis|structure|breakdown)|overview\s*of\s*(the\s*)?project|analyze\s*(the\s*)?project|what\s*(does|is)\s*(this|the)\s*project|describe\s*(the\s*)?project)\b", re.I), Intent.PROJECT_OVERVIEW),
    # Dependency explanation — "import" / "depend" / "dependencies" with or without a file
    (re.compile(
        r"\b("
        r"explain\s*(the\s*)?(imports?|dependencies|deps)\s*(of|for|in)?"
        r"|what\s*(does|do|is|are|will|did)\s+\S+\s*(import|depend|require)"
        r"|\S+\s+(imports?|depends?\s+on|requires?)"
        r"|dependencies?\s*(of|for|in)"
        r"|show\s*(me\s*)?(the\s*)?(imports?|dependencies|deps)"
        r")\b",
        re.I,
    ), Intent.EXPLAIN_DEPENDENCIES),
    # Summarize
    (re.compile(r"\b(summar(ize|ise|y)|brief|briefly|tldr|tl;dr|quick\s*(overview|summary)|in\s*a\s*few\s*words|short\s*(description|summary))\b", re.I), Intent.SUMMARIZE_FILE),
    # Explain / describe / what does
    (re.compile(r"\b(explain|describe|what\s*(does|is|are)\s*(this\s*file\s*do|it\s*do)?|how\s*does\s*(it|this)\s*work|tell\s*me\s*(about|what)|walk\s*me\s*through|show\s*me|review)\b", re.I), Intent.EXPLAIN_FILE),
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
    """
    normalised = text.strip()
    file_ref = _extract_file_reference(normalised)

    # 1. Try intent pattern matching
    for pattern, intent in _INTENT_PATTERNS:
        if pattern.search(normalised):
            # Dependency intent requires a file reference to be meaningful
            if intent == Intent.EXPLAIN_DEPENDENCIES and not file_ref:
                # Fall through to project overview if no file is mentioned
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
            "'Explain dependencies of App.jsx', or 'Give me a project overview'."
        ),
    )
