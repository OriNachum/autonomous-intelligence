"""Tool output size guard to prevent context overflow."""

import os
from typing import Callable

# Configuration
MAX_TOOL_OUTPUT_CHARS = int(os.getenv("QQ_MAX_TOOL_OUTPUT", "28000"))  # ~8K tokens
CHARS_PER_TOKEN = float(os.getenv("QQ_CHARS_PER_TOKEN", "3.5"))


def guard_output(output: str, tool_name: str = "tool") -> str:
    """
    Truncate tool output if it would overwhelm context.

    Args:
        output: The raw tool output string.
        tool_name: Name of the tool (for error message).

    Returns:
        Original output if under limit, truncated with warning otherwise.
    """
    if len(output) <= MAX_TOOL_OUTPUT_CHARS:
        return output

    # Truncate at line boundary
    truncated = output[:MAX_TOOL_OUTPUT_CHARS]
    last_newline = truncated.rfind('\n')
    if last_newline > MAX_TOOL_OUTPUT_CHARS * 0.8:
        truncated = truncated[:last_newline]

    est_tokens = int(len(output) / CHARS_PER_TOKEN)
    shown_tokens = int(len(truncated) / CHARS_PER_TOKEN)

    return (
        f"{truncated}\n\n"
        f"[OUTPUT TRUNCATED]\n"
        f"Tool '{tool_name}' returned ~{est_tokens} tokens, showing first ~{shown_tokens}.\n"
        f"Use more specific parameters or pagination to get remaining data."
    )


def wrap_tool(tool_fn: Callable[..., str], tool_name: str = None) -> Callable[..., str]:
    """
    Wrap a tool function to guard its output.

    Args:
        tool_fn: The tool function to wrap.
        tool_name: Optional name override (defaults to function name).

    Returns:
        Wrapped function with output guarding.
    """
    name = tool_name or getattr(tool_fn, '__name__', 'tool')

    def wrapped(*args, **kwargs) -> str:
        result = tool_fn(*args, **kwargs)
        if isinstance(result, str):
            return guard_output(result, name)
        return result

    # Preserve function metadata
    wrapped.__name__ = tool_fn.__name__
    wrapped.__doc__ = tool_fn.__doc__
    return wrapped
