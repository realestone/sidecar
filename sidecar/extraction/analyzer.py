"""Analyze a filtered session + diff via a single Haiku API call."""

from __future__ import annotations

import json
import os

import anthropic

from ..errors import SidecarError
from .models import CodeDiff, FilteredSession, SessionBriefing
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"
MAX_RETRIES = 2
MAX_INPUT_CHARS = 150000  # ~37,500 tokens, well under the 50k rate limit

ANALYSIS_PROMPT = """You are analyzing a developer's coding session with an AI assistant.
You are given TWO sources of truth:
1. CODEBASE DIFF — what actually changed in the code (the ground truth)
2. CONVERSATION — the developer's messages and AI responses (the context)

The diff tells you WHAT changed. The conversation tells you WHY.
Use both. When they conflict, trust the diff.

Produce a post-session briefing. Be SPECIFIC — reference actual files,
functions, and patterns from the DIFF. Never be generic.

Return JSON with exactly these fields:

{
  "session_summary": "2-3 sentences. What was built/changed. Reference actual file names and functionality from the diff.",

  "what_got_built": [
    {
      "file": "path/to/file.py",
      "description": "What this file does in plain language",
      "key_code": "The most important function/class and what it does",
      "key_decisions": ["Why X pattern was chosen over Y"]
    }
  ],

  "how_pieces_connect": "2-3 sentences explaining the architecture. How do the files relate? What calls what? Reference actual imports and function names.",

  "patterns_used": [
    {
      "pattern": "Name of pattern (e.g., closure-based DI)",
      "where": "file.py:function_name (from the diff)",
      "explained": "What it does and why, in 1-2 sentences."
    }
  ],

  "will_bite_you": {
    "issue": "The single most likely thing to cause problems",
    "where": "file.py:line or function (be precise)",
    "why": "Why this is fragile or non-obvious",
    "what_to_check": "What to look at when it breaks"
  },

  "concepts_touched": [
    {
      "concept": "e.g., SQLite WAL mode",
      "in_code": "Where this concept appears in the actual diff",
      "developer_understood": true,
      "evidence": "From the conversation: what shows understanding"
    }
  ]
}

Respond with ONLY valid JSON, no markdown fencing."""


def analyze_session(
    filtered: FilteredSession,
    diff: CodeDiff,
    project_path: str,
) -> SessionBriefing:
    """Send filtered conversation + diff to Haiku and parse the response.

    Requires ANTHROPIC_API_KEY environment variable.

    Returns:
        SessionBriefing populated from the API response.

    Raises:
        SidecarError: On API or parsing failures.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SidecarError.analyzer_error("ANTHROPIC_API_KEY not set")

    # Build the user message with conversation + diff
    conversation_text = _format_conversation(filtered)
    diff_text = _format_diff(diff)

    user_message = (
        f"## CODEBASE DIFF\n\n{diff_text}\n\n## CONVERSATION\n\n{conversation_text}"
    )

    # Truncate if too long to avoid rate limits
    if len(user_message) > MAX_INPUT_CHARS:
        # Prioritize diff over conversation, truncate conversation
        available_for_conv = MAX_INPUT_CHARS - len(diff_text) - 100  # 100 for headers
        if available_for_conv > 10000:
            conversation_text = conversation_text[:available_for_conv] + "\n\n[...conversation truncated...]"
        else:
            # Both need truncation
            diff_text = diff_text[: MAX_INPUT_CHARS // 2] + "\n\n[...diff truncated...]"
            conversation_text = conversation_text[: MAX_INPUT_CHARS // 2] + "\n\n[...conversation truncated...]"

        user_message = (
            f"## CODEBASE DIFF\n\n{diff_text}\n\n## CONVERSATION\n\n{conversation_text}"
        )

    client = anthropic.Anthropic(api_key=api_key)

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=ANALYSIS_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            text = response.content[0].text
            data = _parse_json(text)

            return SessionBriefing(
                session_id=filtered.session_id,
                project_path=project_path,
                session_summary=data.get("session_summary", ""),
                what_got_built=data.get("what_got_built", []),
                how_pieces_connect=data.get("how_pieces_connect", ""),
                patterns_used=data.get("patterns_used", []),
                will_bite_you=data.get("will_bite_you", {}),
                concepts_touched=data.get("concepts_touched", []),
            )
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            last_error = e
            continue
        except anthropic.RateLimitError as e:
            raise SidecarError.analyzer_error(
                "Rate limit exceeded. Wait a minute and try again, or try a smaller session."
            ) from e
        except anthropic.APIError as e:
            raise SidecarError.analyzer_error(f"API error: {e}") from e

    # All retries failed
    raise SidecarError.analyzer_error(
        f"Failed to parse response after {MAX_RETRIES} attempts: {last_error}"
    )


def _parse_json(text: str) -> dict:
    """Parse JSON from the API response, stripping markdown fencing if present."""
    text = text.strip()
    if text.startswith("```"):
        # Remove ```json ... ``` or ``` ... ```
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    return json.loads(text)


def _format_conversation(filtered: FilteredSession) -> str:
    """Format filtered messages into a readable conversation text."""
    parts: list[str] = []

    for msg in filtered.messages:
        if msg.role == "user":
            text = _extract_text(msg.content)
            if text:
                parts.append(f"USER: {text}")
        elif msg.role == "assistant":
            text = _extract_text(msg.content)
            tools = _extract_tools(msg.content)
            line = f"ASSISTANT: {text}" if text else "ASSISTANT:"
            if tools:
                line += f"\n  [Tools: {', '.join(tools)}]"
            parts.append(line)
        elif msg.type == "summary":
            text = _extract_text(msg.content)
            if text:
                parts.append(f"SESSION SUMMARY: {text}")

    return "\n\n".join(parts)


def _format_diff(diff: CodeDiff) -> str:
    """Format CodeDiff into text for the prompt."""
    if not diff.files:
        return "(no diff available)"

    parts: list[str] = []
    parts.append(
        f"Source: {diff.source} | "
        f"+{diff.total_additions} -{diff.total_deletions} | "
        f"{len(diff.files)} files"
    )
    if diff.truncated:
        parts.append("(diff truncated)")
    parts.append("")

    for f in diff.files:
        if f.diff_text:
            parts.append(f.diff_text)
        else:
            parts.append(f"  {f.status}: {f.path}")

    return "\n".join(parts)


def _extract_text(content: list[dict]) -> str:
    """Extract text blocks from content."""
    texts = []
    for block in content:
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
    return " ".join(texts)


def _extract_tools(content: list[dict]) -> list[str]:
    """Extract tool names from content."""
    tools = []
    for block in content:
        if block.get("type") == "tool_use":
            name = block.get("name", "")
            path = block.get("file_path", "")
            if path:
                tools.append(f"{name}({path})")
            else:
                tools.append(name)
    return tools
