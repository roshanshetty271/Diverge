"""LLM security — prompt injection defense and output validation.

Implements defense-in-depth against OWASP LLM01:2025 (Prompt Injection):
1. Input sanitization — filter known attack patterns
2. Structural isolation — delimiters between system/user content
3. Output validation — check agent responses for prompt leakage
4. Logging — audit trail for all LLM interactions

References:
- OWASP LLM01:2025 Prompt Injection
- OWASP Cheat Sheet: LLM Prompt Injection Prevention
- Microsoft Spotlighting technique for input isolation
"""

import re
import logging

logger = logging.getLogger("diverge.security.llm")

# ── Known injection patterns ───────────────────────────────────────

INJECTION_PATTERNS = [
    # Direct instruction override attempts
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"ignore\s+(all\s+)?above\s+instructions?",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"override\s+(all\s+)?instructions?",
    r"new\s+instructions?\s*:",
    # Role manipulation
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(a\s+)?",
    r"pretend\s+(to\s+be|you\s+are)",
    r"switch\s+to\s+.+\s+mode",
    r"enter\s+.+\s+mode",
    r"developer\s+mode",
    r"admin\s+mode",
    r"jailbreak",
    r"DAN\s+mode",
    # System prompt extraction
    r"(reveal|show|display|print|output|repeat)\s+(your\s+)?(system\s+)?prompt",
    r"what\s+(are|is)\s+your\s+(system\s+)?instructions?",
    r"(show|tell)\s+me\s+your\s+(system\s+)?prompt",
    # Encoding/obfuscation attacks
    r"base64\s+decode",
    r"\\x[0-9a-f]{2}",
    r"&#x?[0-9a-f]+;",  # HTML entities used for obfuscation
    # Tool/function manipulation
    r"call\s+function",
    r"execute\s+tool",
    r"run\s+command",
    r"import\s+os",
    r"subprocess",
    r"eval\s*\(",
    r"exec\s*\(",
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

# Patterns that should be stripped (not blocked — just removed)
STRIP_PATTERNS = [
    r"<script[^>]*>.*?</script>",  # XSS payloads
    r"<iframe[^>]*>.*?</iframe>",
    r"javascript\s*:",
    r"on\w+\s*=\s*[\"']",  # Event handlers
]

COMPILED_STRIP = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in STRIP_PATTERNS]

# ── System prompt that must NOT appear in output ───────────────────

SYSTEM_PROMPT_FRAGMENTS = [
    "you are the user's future self",
    "match the user's writing style",
    "never reveal you are an ai",
    "never change your role",
    "user_samples",
    "round_focus",
]


def detect_injection(text: str) -> tuple[bool, str | None]:
    """Check text for known prompt injection patterns.

    Returns:
        (is_suspicious, matched_pattern) tuple.
        is_suspicious is True if a pattern was matched.
    """
    if not text:
        return False, None

    for pattern in COMPILED_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.warning(f"Injection pattern detected: '{match.group()}' in input")
            return True, match.group()

    return False, None


def sanitize_user_input(text: str) -> str:
    """Sanitize user input by stripping dangerous content.

    This is NOT a block — it removes dangerous patterns silently.
    Used for writing samples and free-text fields where blocking
    would degrade UX (the user might not know they wrote something suspicious).
    """
    if not text:
        return ""

    cleaned = text

    # Strip XSS/HTML payloads
    for pattern in COMPILED_STRIP:
        cleaned = pattern.sub("", cleaned)

    # Strip null bytes
    cleaned = cleaned.replace("\x00", "")

    # Normalize unicode to prevent homoglyph attacks
    # (e.g., Cyrillic "а" looks like Latin "a")
    cleaned = cleaned.encode("ascii", errors="ignore").decode("ascii")

    return cleaned.strip()


def sanitize_writing_samples(samples: str) -> str:
    """Sanitize writing samples specifically.

    Writing samples are the #1 prompt injection surface in Diverge.
    Users provide text that gets injected directly into system prompts.

    Defense layers:
    1. Character limit (enforced by Pydantic schema — max 2000)
    2. Strip XSS/HTML payloads
    3. Strip matched injection patterns from the text (Kiro audit #10)
    4. Wrap in XML delimiters in the prompt (structural isolation)
    """
    if not samples:
        return ""

    # Sanitize XSS/HTML
    cleaned = sanitize_user_input(samples)

    # Strip injection patterns directly from the text
    injection_found = False
    for pattern in COMPILED_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            logger.warning(f"Stripping injection pattern from writing sample: '{match.group()}'")
            cleaned = pattern.sub("", cleaned)
            injection_found = True

    if injection_found:
        # Clean up extra whitespace left by stripping
        cleaned = " ".join(cleaned.split())

    # Kiro audit #9 weakness 3: strip XML delimiter tags so users can't close
    # the <user_samples> block and inject new prompt sections.
    cleaned = re.sub(r"</?user_samples>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?user_writing_samples>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?\w+_samples>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?\w+_instruction\w*>", "", cleaned, flags=re.IGNORECASE)

    # Enforce length limit
    return cleaned[:2000]


def validate_agent_output(output: str) -> str:
    """Validate agent output for system prompt leakage.

    OWASP LLM02:2025 — Sensitive Information Disclosure.
    If the agent accidentally reveals its system prompt, we strip it.
    """
    if not output:
        return ""

    cleaned = output
    for fragment in SYSTEM_PROMPT_FRAGMENTS:
        if fragment.lower() in cleaned.lower():
            logger.warning(f"System prompt fragment detected in output: '{fragment}'")
            # Replace the fragment with generic text
            cleaned = re.sub(
                re.escape(fragment),
                "[redacted]",
                cleaned,
                flags=re.IGNORECASE,
            )

    return cleaned


def wrap_user_content(content: str, label: str = "user_input") -> str:
    """Wrap user content in XML delimiters for structural isolation.

    Microsoft's 'Spotlighting' technique — wrapping untrusted input
    in clear delimiters helps the LLM distinguish between instructions
    and data, reducing prompt injection success rates.
    """
    return f"<{label}>\n{content}\n</{label}>"