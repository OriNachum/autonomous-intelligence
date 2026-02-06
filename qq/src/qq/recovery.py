"""Token limit recovery - retry with progressively reduced context."""

import logging
from typing import Any, Callable, Optional, List
from dataclasses import dataclass, field

from qq.errors import parse_token_error, TokenLimitInfo, classify_overflow

logger = logging.getLogger("qq.recovery")


@dataclass
class RecoveryResult:
    """Result of agent execution with recovery."""
    success: bool
    response: Optional[Any] = None
    attempts: int = 0
    strategy: str = "normal"
    tokens_reduced: int = 0
    error: Optional[Exception] = None
    warnings: List[str] = field(default_factory=list)
    overflow_severity: str = "none"  # none, minor, major, catastrophic, unknown


class TokenRecovery:
    """
    Execute agent calls with automatic recovery from token limits.

    Strategy: Progressively reduce history window on each retry.
    Window sizes: 20 → 10 → 5 → 2 → 0 (current message only)
    """

    WINDOW_SIZES = [20, 10, 5, 2, 0]

    def __init__(self, history, max_retries: int = 4):
        """
        Args:
            history: ConversationHistory instance
            max_retries: Maximum recovery attempts
        """
        self.history = history
        self.max_retries = max_retries
        self.original_window = getattr(history, 'window_size', 20)

    def execute(
        self,
        agent_fn: Callable[[str], Any],
        message: str,
        on_retry: Optional[Callable[[int, str], None]] = None,
    ) -> RecoveryResult:
        """
        Execute agent with automatic token limit recovery.

        Args:
            agent_fn: Function that calls the agent
            message: User message to process
            on_retry: Optional callback(attempt, strategy) on each retry

        Returns:
            RecoveryResult with success status and response
        """
        attempt = 0
        last_error = None
        last_info: Optional[TokenLimitInfo] = None

        while attempt <= self.max_retries:
            try:
                # Set window size for this attempt
                window = self._get_window_for_attempt(attempt)
                if hasattr(self.history, 'window_size'):
                    self.history.window_size = window

                # Execute
                response = agent_fn(message)

                # Success
                return RecoveryResult(
                    success=True,
                    response=response,
                    attempts=attempt + 1,
                    strategy=self._strategy_name(attempt),
                    tokens_reduced=self._tokens_saved(attempt, last_info),
                )

            except Exception as e:
                is_token, info = parse_token_error(e)

                if not is_token:
                    # Not a token error - don't retry
                    return RecoveryResult(
                        success=False,
                        error=e,
                        attempts=attempt + 1,
                        strategy=self._strategy_name(attempt),
                    )

                severity = classify_overflow(info)
                last_error = e
                last_info = info

                logger.warning(
                    f"Token limit hit (attempt {attempt + 1}): "
                    f"{info.overflow if info else '?'} tokens over, severity: {severity}"
                )

                # For catastrophic overflow, don't bother retrying - history reduction won't help
                if severity == 'catastrophic':
                    return RecoveryResult(
                        success=False,
                        error=e,
                        attempts=attempt + 1,
                        strategy="tool_output_overflow",
                        overflow_severity=severity,
                        warnings=[
                            "A tool returned too much data for the context window.",
                            "Use more specific parameters or pagination.",
                        ],
                    )

                if on_retry:
                    on_retry(attempt + 1, self._strategy_name(attempt + 1))

                attempt += 1

        # All retries exhausted
        severity = classify_overflow(last_info) if last_info else 'unknown'
        return RecoveryResult(
            success=False,
            error=last_error,
            attempts=attempt,
            strategy="exhausted",
            overflow_severity=severity,
            warnings=[
                "Token limit recovery exhausted",
                f"Last overflow: {last_info.overflow if last_info else 'unknown'} tokens",
            ],
        )

    def _get_window_for_attempt(self, attempt: int) -> int:
        """Get history window size for attempt number."""
        if attempt < len(self.WINDOW_SIZES):
            return self.WINDOW_SIZES[attempt]
        return 0  # Last resort: no history

    def _strategy_name(self, attempt: int) -> str:
        """Human-readable strategy name."""
        if attempt == 0:
            return "normal"
        elif attempt < len(self.WINDOW_SIZES):
            return f"window_{self.WINDOW_SIZES[attempt]}"
        else:
            return "minimal"

    def _tokens_saved(self, attempt: int, info: Optional[TokenLimitInfo]) -> int:
        """Estimate tokens saved by reduction."""
        if attempt == 0:
            return 0
        if info:
            return info.overflow + 500  # Buffer
        # Rough estimate: ~500 tokens per message
        window_diff = self.original_window - self._get_window_for_attempt(attempt)
        return window_diff * 500

    def reset(self):
        """Reset history window to original size."""
        if hasattr(self.history, 'window_size'):
            self.history.window_size = self.original_window


def execute_with_recovery(
    agent_fn: Callable[[str], Any],
    message: str,
    history,
    max_retries: int = 4,
    on_retry: Optional[Callable[[int, str], None]] = None,
) -> RecoveryResult:
    """
    Convenience function for single-use recovery.

    Args:
        agent_fn: Function that calls the agent
        message: User message
        history: ConversationHistory instance
        max_retries: Max recovery attempts
        on_retry: Optional callback on retry

    Returns:
        RecoveryResult
    """
    recovery = TokenRecovery(history, max_retries)
    try:
        return recovery.execute(agent_fn, message, on_retry)
    finally:
        recovery.reset()
