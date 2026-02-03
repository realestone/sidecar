"""Filter session messages to reduce noise while preserving signal."""

from __future__ import annotations

from .models import FilteredSession, FilterStats, SessionMessage

# Thresholds from spec
SHORT_ASSISTANT_THRESHOLD = 50  # chars — remove short assistant msgs
LONG_ASSISTANT_THRESHOLD = 500  # chars — truncate long assistant msgs
TRUNCATE_TO = 300  # chars — truncation target
BASH_COMMAND_PREVIEW = 100  # chars — keep first N chars of bash commands

# Tool names whose file_path we preserve
FILE_TOOLS = {"Write", "Edit", "Read"}

# Message types to remove entirely
REMOVE_TYPES = {"progress", "file-history-snapshot"}


def filter_session(
    session_id: str,
    messages: list[SessionMessage],
) -> FilteredSession:
    """Apply spec filter rules to reduce messages to high-signal content.

    Rules:
        - type "progress" / "file-history-snapshot": remove entirely
        - type "summary": keep
        - Short assistant msgs (<50 chars): remove
        - Write/Edit tool_use blocks: keep file path + tool name, strip content
        - Other tool_use blocks: keep name only, strip content
        - Long assistant msgs (>500 chars): truncate to 300 chars
        - User messages: keep in full
    """
    stats = FilterStats(original_count=len(messages))
    kept: list[SessionMessage] = []

    for msg in messages:
        # Remove progress and file-history-snapshot
        if msg.type in REMOVE_TYPES:
            if msg.type == "progress":
                stats.removed_progress += 1
            else:
                stats.removed_file_history += 1
            continue

        # Keep summary messages as-is
        if msg.type == "summary":
            kept.append(msg)
            continue

        # Keep user messages in full
        if msg.role == "user":
            kept.append(msg)
            continue

        # Assistant messages: apply filtering
        if msg.role == "assistant":
            filtered_content = _filter_assistant_content(msg.content, stats)
            if not filtered_content:
                continue

            # Check if it's only a short text response
            text_only = [b for b in filtered_content if b.get("type") == "text"]
            if (
                len(filtered_content) == len(text_only)
                and all(
                    len(b.get("text", "")) < SHORT_ASSISTANT_THRESHOLD
                    for b in text_only
                )
            ):
                continue

            kept.append(
                SessionMessage(
                    type=msg.type,
                    uuid=msg.uuid,
                    parent_uuid=msg.parent_uuid,
                    timestamp=msg.timestamp,
                    role=msg.role,
                    content=filtered_content,
                    raw={},  # Don't keep raw in filtered output
                )
            )
            continue

        # Other message types (queue-operation, etc.): skip
        continue

    stats.kept_count = len(kept)

    return FilteredSession(
        session_id=session_id,
        messages=kept,
        stats=stats,
    )


def _filter_assistant_content(
    content: list[dict],
    stats: FilterStats,
) -> list[dict]:
    """Filter individual content blocks from an assistant message."""
    result: list[dict] = []

    for block in content:
        block_type = block.get("type", "")

        if block_type == "text":
            text = block.get("text", "")
            if len(text) > LONG_ASSISTANT_THRESHOLD:
                stats.truncated_messages += 1
                result.append({"type": "text", "text": text[:TRUNCATE_TO] + "..."})
            else:
                result.append(block)

        elif block_type == "tool_use":
            stats.stripped_tool_content += 1
            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            if tool_name in FILE_TOOLS:
                # Keep file path + tool name
                result.append(
                    {
                        "type": "tool_use",
                        "name": tool_name,
                        "file_path": tool_input.get("file_path", ""),
                    }
                )
            elif tool_name == "Bash":
                # Keep description + command preview
                result.append(
                    {
                        "type": "tool_use",
                        "name": tool_name,
                        "description": tool_input.get("description", ""),
                        "command_preview": tool_input.get("command", "")[
                            :BASH_COMMAND_PREVIEW
                        ],
                    }
                )
            else:
                # Other tools: keep name only
                result.append({"type": "tool_use", "name": tool_name})

        elif block_type == "tool_result":
            # Tool results from user messages pass through in user handling
            # If somehow here, strip to minimal
            result.append(
                {"type": "tool_result", "tool_use_id": block.get("tool_use_id", "")}
            )

        else:
            result.append(block)

    return result
