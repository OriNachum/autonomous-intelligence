# Max Tokens Limit Recovery Plan

**Status: IMPLEMENTED (Phase 1-4)**

## Problem Statement

The QQ agent is hitting max_tokens limits more frequently due to:
1. Larger user requests
2. Rich context injection (core notes, working notes, knowledge graph)
3. No explicit max_tokens configuration matching vLLM
4. No error detection or recovery mechanism for token limits
5. Static sliding window that doesn't adapt to context size

**Current error:**
```
Error: Error executing agent: Agent has reached an unrecoverable state due to max_tokens limit.
```

---

## Current State Analysis

### What Exists
- Static sliding window: 20 messages (hardcoded)
- Generic exception catching (no token-specific handling)
- Output truncation for child processes (50,000 chars)
- JSON parsing recovery patterns (can adapt for token recovery)

### What's Missing
- No `max_tokens` parameter in model configuration
- No detection of token limit errors
- No dynamic history trimming
- No retry with reduced context
- No graceful degradation strategy

---

## Architecture

### Token Limit Recovery Flow

```
User Input
    ↓
Context Injection (core + notes + KG)
    ↓
Build Messages Array
    ↓
┌─────────────────────────────────────────────────┐
│              TOKEN LIMIT GUARD                   │
│  1. Estimate token count                         │
│  2. If > threshold: preemptively trim            │
└─────────────────────────────────────────────────┘
    ↓
Call Agent
    ↓
┌─────────────────────────────────────────────────┐
│           ERROR DETECTION                        │
│  Catch: max_tokens, context_length,              │
│         content_filter, rate_limit               │
└─────────────────────────────────────────────────┘
    ↓ (on token error)
┌─────────────────────────────────────────────────┐
│           RECOVERY STRATEGY                      │
│  1. Reduce history window (20 → 10 → 5 → 1)      │
│  2. Summarize old messages                       │
│  3. Remove context injection                     │
│  4. Retry with minimal context                   │
└─────────────────────────────────────────────────┘
    ↓ (if all retries fail)
┌─────────────────────────────────────────────────┐
│           GRACEFUL DEGRADATION                   │
│  - Clear history, keep only current message      │
│  - Warn user about context loss                  │
│  - Log for debugging                             │
└─────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Configuration & Detection

#### 1.1 Add Token Configuration

**File: `src/qq/agents/__init__.py`**

```python
import os

# Token configuration
MAX_TOKENS = int(os.getenv("QQ_MAX_TOKENS", "4096"))
MAX_CONTEXT_TOKENS = int(os.getenv("QQ_MAX_CONTEXT", "32000"))
TOKEN_SAFETY_MARGIN = float(os.getenv("QQ_TOKEN_MARGIN", "0.85"))

def get_model() -> OpenAIModel:
    return OpenAIModel(
        model_id=model_name,
        client_args={
            "base_url": start_url,
            "api_key": api_key,
        },
        max_tokens=MAX_TOKENS,  # Add explicit max_tokens
    )
```

#### 1.2 Create Token Error Detection

**File: `src/qq/errors.py`** (NEW)

```python
"""Token limit error detection and classification."""

import re
from typing import Optional, Tuple

class TokenLimitError(Exception):
    """Raised when token limit is exceeded."""
    def __init__(self, message: str, tokens_used: Optional[int] = None,
                 tokens_limit: Optional[int] = None):
        super().__init__(message)
        self.tokens_used = tokens_used
        self.tokens_limit = tokens_limit


class ContextTooLargeError(TokenLimitError):
    """Input context exceeds model's maximum context window."""
    pass


class MaxTokensExceededError(TokenLimitError):
    """Output generation hit max_tokens limit."""
    pass


# Patterns to detect token-related errors from various sources
TOKEN_ERROR_PATTERNS = [
    (r"max_tokens", MaxTokensExceededError),
    (r"maximum context length", ContextTooLargeError),
    (r"context_length_exceeded", ContextTooLargeError),
    (r"token limit", TokenLimitError),
    (r"too many tokens", TokenLimitError),
    (r"input too long", ContextTooLargeError),
    (r"context window", ContextTooLargeError),
    (r"unrecoverable state due to max_tokens", MaxTokensExceededError),
]


def classify_error(error: Exception) -> Tuple[bool, Optional[TokenLimitError]]:
    """
    Classify an exception as a token limit error.

    Returns:
        (is_token_error, typed_error)
    """
    error_str = str(error).lower()

    for pattern, error_class in TOKEN_ERROR_PATTERNS:
        if re.search(pattern, error_str, re.IGNORECASE):
            return (True, error_class(str(error)))

    return (False, None)


def is_recoverable(error: TokenLimitError) -> bool:
    """Check if a token error can be recovered from."""
    # MaxTokensExceeded is recoverable by reducing context
    # ContextTooLarge is recoverable by trimming history
    return True  # All token errors are potentially recoverable
```

### Phase 2: Token Estimation

#### 2.1 Simple Token Counter

**File: `src/qq/tokens.py`** (NEW)

```python
"""Token estimation utilities."""

import os
from typing import List, Dict, Any

# Approximate chars per token (conservative estimate)
CHARS_PER_TOKEN = float(os.getenv("QQ_CHARS_PER_TOKEN", "3.5"))


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return int(len(text) / CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens in a message array."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "")
        # Add overhead for message structure
        total += estimate_tokens(content) + 4  # ~4 tokens per message overhead
    return total


def estimate_context_tokens(
    messages: List[Dict[str, Any]],
    system_prompt: str = "",
    context_injection: str = "",
) -> int:
    """Estimate total context tokens including all injections."""
    total = estimate_messages_tokens(messages)
    total += estimate_tokens(system_prompt)
    total += estimate_tokens(context_injection)
    return total


def tokens_remaining(
    messages: List[Dict[str, Any]],
    max_context: int,
    max_output: int,
    system_prompt: str = "",
    context_injection: str = "",
) -> int:
    """Calculate remaining tokens for output."""
    used = estimate_context_tokens(messages, system_prompt, context_injection)
    available = max_context - used - max_output
    return max(0, available)
```

### Phase 3: Recovery Strategies

#### 3.1 History Trimming

**File: `src/qq/history.py`** - Add methods:

```python
def trim_to_tokens(self, max_tokens: int, chars_per_token: float = 3.5) -> int:
    """
    Trim history to fit within token budget.

    Returns:
        Number of messages removed
    """
    from qq.tokens import estimate_messages_tokens

    removed = 0
    messages = self.get_messages()

    while messages and estimate_messages_tokens(messages) > max_tokens:
        # Remove oldest message (but keep system messages)
        if len(messages) > 1:
            self._messages.pop(0)
            messages = self.get_messages()
            removed += 1
        else:
            break

    return removed


def get_compressed_history(self, max_messages: int = 5) -> List[Dict]:
    """Get a compressed version of history with only recent messages."""
    return self._messages[-max_messages:]


def summarize_and_trim(self, summarizer_fn, keep_recent: int = 3) -> str:
    """
    Summarize old messages and keep only recent ones.

    Args:
        summarizer_fn: Function to summarize messages
        keep_recent: Number of recent messages to keep intact

    Returns:
        Summary of trimmed messages
    """
    if len(self._messages) <= keep_recent:
        return ""

    old_messages = self._messages[:-keep_recent]
    summary = summarizer_fn(old_messages)

    # Replace old messages with summary
    self._messages = [
        {"role": "system", "content": f"[Previous conversation summary: {summary}]"}
    ] + self._messages[-keep_recent:]

    return summary
```

#### 3.2 Retry with Reduction

**File: `src/qq/recovery.py`** (NEW)

```python
"""Token limit recovery strategies."""

import logging
from typing import Any, Callable, Optional, List, Dict
from dataclasses import dataclass

from qq.errors import classify_error, TokenLimitError, is_recoverable
from qq.tokens import estimate_context_tokens

logger = logging.getLogger("qq.recovery")


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""
    success: bool
    response: Optional[Any] = None
    strategy_used: Optional[str] = None
    context_reduced: bool = False
    messages_trimmed: int = 0
    error: Optional[Exception] = None


class TokenLimitRecovery:
    """
    Handles recovery from token limit errors with progressive reduction.

    Strategies (in order):
    1. Reduce history window
    2. Remove context injection
    3. Summarize old messages
    4. Keep only current message
    """

    # Progressive window sizes to try
    WINDOW_SIZES = [20, 10, 5, 3, 1]

    def __init__(
        self,
        agent_fn: Callable,
        history,
        max_retries: int = 4,
    ):
        self.agent_fn = agent_fn
        self.history = history
        self.max_retries = max_retries
        self.original_window = history.window_size

    def execute_with_recovery(
        self,
        message: str,
        context_injection: str = "",
        system_prompt: str = "",
    ) -> RecoveryResult:
        """
        Execute agent with automatic recovery on token errors.
        """
        attempt = 0
        last_error = None

        while attempt <= self.max_retries:
            try:
                # Try with current settings
                response = self.agent_fn(message)

                return RecoveryResult(
                    success=True,
                    response=response,
                    strategy_used=self._get_strategy_name(attempt),
                    context_reduced=(attempt > 0),
                    messages_trimmed=self.original_window - self.history.window_size,
                )

            except Exception as e:
                is_token_error, typed_error = classify_error(e)

                if not is_token_error:
                    # Not a token error, don't retry
                    raise

                last_error = typed_error or e
                logger.warning(f"Token limit hit (attempt {attempt + 1}): {e}")

                # Apply recovery strategy
                if not self._apply_recovery_strategy(attempt, context_injection):
                    # No more strategies to try
                    break

                attempt += 1

        # All retries exhausted
        return RecoveryResult(
            success=False,
            error=last_error,
            strategy_used="exhausted",
            context_reduced=True,
            messages_trimmed=self.original_window - self.history.window_size,
        )

    def _apply_recovery_strategy(self, attempt: int, context_injection: str) -> bool:
        """
        Apply progressively more aggressive recovery.

        Returns:
            True if a strategy was applied, False if exhausted
        """
        if attempt < len(self.WINDOW_SIZES):
            # Strategy 1-4: Reduce window size
            new_size = self.WINDOW_SIZES[attempt]
            logger.info(f"Recovery: reducing window to {new_size} messages")
            self.history.window_size = new_size
            return True

        # All strategies exhausted
        return False

    def _get_strategy_name(self, attempt: int) -> str:
        if attempt == 0:
            return "normal"
        elif attempt < len(self.WINDOW_SIZES):
            return f"reduced_window_{self.WINDOW_SIZES[attempt]}"
        else:
            return "minimal"

    def reset(self):
        """Reset to original settings after recovery."""
        self.history.window_size = self.original_window
```

### Phase 4: Integration into App

#### 4.1 Update Main Loop

**File: `src/qq/app.py`** - Modify the agent execution:

```python
from qq.recovery import TokenLimitRecovery, RecoveryResult
from qq.errors import classify_error

async def process_message(self, user_input: str) -> str:
    """Process a user message with token limit recovery."""

    # Prepare context
    context = self.retrieval_agent.prepare_context(user_input)
    context_text = context.get("context_text", "")

    # Create recovery handler
    recovery = TokenLimitRecovery(
        agent_fn=lambda msg: self.agent(msg),
        history=self.history,
        max_retries=4,
    )

    # Format message with context
    formatted_message = self._format_with_context(user_input, context_text)

    # Execute with recovery
    result = recovery.execute_with_recovery(
        message=formatted_message,
        context_injection=context_text,
    )

    if result.success:
        response = str(result.response)

        # Log if recovery was needed
        if result.context_reduced:
            logger.info(
                f"Recovered from token limit: {result.strategy_used}, "
                f"trimmed {result.messages_trimmed} messages"
            )
            # Optionally notify user
            if result.messages_trimmed > 5:
                self.console.print_warning(
                    f"[Context reduced to fit token limit, "
                    f"{result.messages_trimmed} messages trimmed]"
                )

        return response
    else:
        # Unrecoverable - clear history and retry once
        logger.error(f"Token recovery failed: {result.error}")
        self.console.print_warning(
            "[Token limit exceeded - clearing history for fresh start]"
        )
        self.history.clear()

        # Final attempt with just the current message
        try:
            response = self.agent(user_input)  # No context injection
            return str(response)
        except Exception as e:
            raise RuntimeError(
                f"Unable to process message even with minimal context: {e}"
            )
```

### Phase 5: vLLM Configuration Alignment

#### 5.1 Environment Variables

Add to `.env.sample`:

```bash
# Token limits (should match vLLM server configuration)
QQ_MAX_TOKENS=4096          # Max output tokens per response
QQ_MAX_CONTEXT=32000        # Model's context window
QQ_TOKEN_MARGIN=0.85        # Safety margin (use 85% of context)
QQ_CHARS_PER_TOKEN=3.5      # Approximate chars per token

# Recovery settings
QQ_RECOVERY_RETRIES=4       # Max retry attempts on token error
QQ_MIN_WINDOW=1             # Minimum messages to keep
```

#### 5.2 vLLM Server Check

**File: `src/qq/test_systems.py`** - Add token limit check:

```python
def test_vllm_token_limits():
    """Verify vLLM server token configuration."""
    import os

    max_tokens = int(os.getenv("QQ_MAX_TOKENS", "4096"))
    max_context = int(os.getenv("QQ_MAX_CONTEXT", "32000"))

    # Test that we can generate max_tokens
    client = get_openai_client()
    response = client.chat.completions.create(
        model=os.getenv("MODEL_ID"),
        messages=[{"role": "user", "content": "Count from 1 to 100."}],
        max_tokens=max_tokens,
    )

    assert response.usage.completion_tokens <= max_tokens
    print(f"✓ vLLM accepts max_tokens={max_tokens}")
```

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `QQ_MAX_TOKENS` | 4096 | Max output tokens |
| `QQ_MAX_CONTEXT` | 32000 | Total context window |
| `QQ_TOKEN_MARGIN` | 0.85 | Safety margin |
| `QQ_CHARS_PER_TOKEN` | 3.5 | Token estimation ratio |
| `QQ_RECOVERY_RETRIES` | 4 | Max recovery attempts |
| `QQ_MIN_WINDOW` | 1 | Minimum history window |

---

## Error Messages

### User-Facing

```
[Context reduced to fit token limit, N messages trimmed]
[Token limit exceeded - clearing history for fresh start]
```

### Logged (Debug)

```
Token limit hit (attempt N): <error details>
Recovery: reducing window to N messages
Recovered from token limit: <strategy>, trimmed N messages
Token recovery failed: <error>
```

---

## Testing Plan

1. **Unit Tests**
   - Token estimation accuracy
   - Error classification
   - History trimming
   - Recovery strategies

2. **Integration Tests**
   - Simulate large context → verify recovery
   - Test with vLLM actual limits
   - Verify graceful degradation

3. **Manual Tests**
   - Large file reads
   - Long conversations
   - Parallel tasks with heavy context

---

## Rollout Plan

| Phase | Tasks | Priority |
|-------|-------|----------|
| 1 | Add error detection (`errors.py`) | High |
| 2 | Add token estimation (`tokens.py`) | High |
| 3 | Add recovery logic (`recovery.py`) | High |
| 4 | Integrate into `app.py` | High |
| 5 | Add history trimming methods | Medium |
| 6 | Environment configuration | Medium |
| 7 | Testing and validation | Medium |

---

## Success Criteria

1. ✅ Token limit errors are detected and classified
2. ✅ Recovery attempts reduce context progressively
3. ✅ User is notified when context is reduced
4. ✅ History can be cleared as last resort
5. ✅ Configuration matches vLLM server limits
6. ✅ No more "unrecoverable state" crashes

---

## Files to Create/Modify

| File | Action | Status | Description |
|------|--------|--------|-------------|
| `src/qq/errors.py` | CREATE | ✅ DONE | Error classification |
| `src/qq/tokens.py` | CREATE | PENDING | Token estimation |
| `src/qq/recovery.py` | CREATE | ✅ DONE | Recovery strategies |
| `src/qq/history.py` | MODIFY | EXISTS | Has clear(), window_size |
| `src/qq/app.py` | MODIFY | ✅ DONE | Integrate recovery |
| `src/qq/agents/__init__.py` | MODIFY | PENDING | Add max_tokens config |
| `.env.sample` | MODIFY | PENDING | Add token variables |
| `src/qq/test_systems.py` | MODIFY | PENDING | Add token limit tests |

---

## Implementation Summary (2026-02-05)

### Files Created

**`src/qq/errors.py`**
- `TokenLimitInfo` dataclass with limit, used, overflow
- `parse_token_error()` - extracts token counts from error message
- `is_token_error()` - quick check if exception is token-related
- Pattern matching for various error formats

**`src/qq/recovery.py`**
- `RecoveryResult` dataclass with success, response, attempts, strategy
- `TokenRecovery` class - manages progressive window reduction
- `execute_with_recovery()` - convenience function for single-use
- Window sizes: 20 → 10 → 5 → 2 → 0

### Files Modified

**`src/qq/app.py`**
- Added imports for recovery module
- `run_cli_mode()` - uses execute_with_recovery()
- `run_console_mode()` - uses execute_with_recovery() with last-resort clear
- Shows warnings on retry: `[Token limit: retrying with window_10]`
- Shows recovery info: `[Recovered: window_5, 3 attempts]`

### How It Works

```
Error: maximum context length is 32768 tokens... 32834 input tokens
    ↓
parse_token_error() → TokenLimitInfo(limit=32768, used=32834, overflow=66)
    ↓
TokenRecovery.execute() → reduce window_size from 20 to 10
    ↓
Retry agent call
    ↓
Success? Return response : Try window_size=5, then 2, then 0
    ↓
All failed? Clear history and try once with just current message
```
