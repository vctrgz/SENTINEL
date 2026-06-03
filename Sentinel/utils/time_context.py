from __future__ import annotations

from datetime import datetime


def get_current_time_context() -> dict:
    """
    Resolve the current local datetime at call time.
    This is intentionally evaluated per prompt so agents can reason about
    freshness-sensitive requests using an up-to-date clock.
    """
    now = datetime.now().astimezone()
    offset = now.strftime("%z")
    offset_fmt = f"{offset[:3]}:{offset[3:]}" if offset else ""

    return {
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "timezone": str(now.tzinfo or "local"),
        "utc_offset": offset_fmt,
        "human": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def build_time_context_block(context: dict | None = None) -> str:
    ctx = context or get_current_time_context()
    return (
        "Runtime Time Context:\n"
        f"- Current local date: {ctx.get('date', '')}\n"
        f"- Current local time: {ctx.get('time', '')}\n"
        f"- Timezone: {ctx.get('timezone', '')}\n"
        f"- UTC offset: {ctx.get('utc_offset', '')}\n"
        f"- ISO timestamp: {ctx.get('iso', '')}"
    )
