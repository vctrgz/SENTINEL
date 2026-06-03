from __future__ import annotations

from typing import Iterable

from utils.language_context import get_language_instruction
from utils.os_context import build_os_context_block, detect_os_context
from utils.time_context import build_time_context_block, get_current_time_context


def build_runtime_context_block(
    extra_lines: Iterable[str] | None = None,
    time_context: dict | None = None,
    os_context: dict | None = None,
    language_context: dict | None = None,
) -> str:
    lines = [
        build_time_context_block(time_context or get_current_time_context()),
        build_os_context_block(os_context or detect_os_context()),
        f"Language Policy: {get_language_instruction(language_context)}",
    ]
    if extra_lines:
        lines.append("Additional Runtime Context:")
        lines.extend(f"- {line}" for line in extra_lines if line)
    return "\n".join(lines)
