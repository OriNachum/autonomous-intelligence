"""Token limit error detection and recovery."""

import re
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class TokenLimitInfo:
    """Information about a token limit error."""
    limit: int
    used: int
    overflow: int

    @property
    def reduction_needed(self) -> float:
        """Fraction of tokens that need to be removed."""
        return self.overflow / self.used if self.used > 0 else 0.5


class TokenLimitError(Exception):
    """Raised when token limit is exceeded."""
    def __init__(self, message: str, info: Optional[TokenLimitInfo] = None):
        super().__init__(message)
        self.info = info


# Pattern to extract token counts from error message
TOKEN_ERROR_PATTERN = re.compile(
    r"maximum context length is (\d+) tokens.*?(\d+) input tokens",
    re.IGNORECASE | re.DOTALL
)

# Patterns that indicate token-related errors
TOKEN_ERROR_INDICATORS = [
    r"maximum context length",
    r"context_length_exceeded",
    r"max_tokens",
    r"token limit",
    r"too many tokens",
    r"input too long",
    r"reduce the length",
]


def parse_token_error(error: Exception) -> Tuple[bool, Optional[TokenLimitInfo]]:
    """
    Parse an exception to extract token limit information.

    Returns:
        (is_token_error, token_info)
    """
    error_str = str(error)

    # Check if it's a token-related error
    is_token_error = any(
        re.search(pattern, error_str, re.IGNORECASE)
        for pattern in TOKEN_ERROR_INDICATORS
    )

    if not is_token_error:
        return (False, None)

    # Try to extract exact numbers
    match = TOKEN_ERROR_PATTERN.search(error_str)
    if match:
        limit = int(match.group(1))
        used = int(match.group(2))
        return (True, TokenLimitInfo(
            limit=limit,
            used=used,
            overflow=used - limit,
        ))

    # Token error but couldn't parse numbers
    return (True, None)


def is_token_error(error: Exception) -> bool:
    """Quick check if an exception is token-related."""
    is_token, _ = parse_token_error(error)
    return is_token


def classify_overflow(info: Optional[TokenLimitInfo]) -> str:
    """
    Classify the severity of token overflow.

    Args:
        info: TokenLimitInfo from parse_token_error, or None.

    Returns:
        'unknown': info is None
        'minor': <1000 tokens over, history reduction may help
        'major': 1000-50000 tokens over, aggressive reduction needed
        'catastrophic': >50000 tokens over, likely tool output problem
    """
    if info is None:
        return 'unknown'

    if info.overflow < 1000:
        return 'minor'
    elif info.overflow < 50000:
        return 'major'
    else:
        return 'catastrophic'
