"""Output summarization for child process results.

Compresses large outputs to prevent token limit issues while
preserving essential information.
"""

import os
import logging
from typing import Optional

from strands import Agent
from strands.models import OpenAIModel


logger = logging.getLogger("summarizer")

# Default threshold: summarize outputs larger than this
DEFAULT_THRESHOLD = int(os.environ.get("QQ_SUMMARIZE_THRESHOLD", "2000"))

# Target size for summarized output
DEFAULT_TARGET_SIZE = int(os.environ.get("QQ_SUMMARIZE_TARGET", "800"))

SUMMARIZE_PROMPT = """You are a summarization assistant. Your task is to compress the given output while preserving ALL essential information.

Rules:
1. Preserve key findings, results, data points, and conclusions
2. Keep specific names, numbers, dates, and identifiers
3. Remove verbose explanations, redundant text, and filler
4. Use bullet points for lists of items
5. If there are errors or warnings, preserve them exactly
6. Keep the summary under {target_size} characters

Output the summary directly with no preamble."""


class OutputSummarizer:
    """Summarizes large outputs using an LLM."""

    def __init__(
        self,
        threshold: int = DEFAULT_THRESHOLD,
        target_size: int = DEFAULT_TARGET_SIZE,
    ):
        """Initialize summarizer.

        Args:
            threshold: Summarize outputs larger than this (chars).
            target_size: Target size for summarized output (chars).
        """
        self.threshold = threshold
        self.target_size = target_size
        self._agent: Optional[Agent] = None

    def _get_agent(self) -> Agent:
        """Lazy-load the summarization agent."""
        if self._agent is None:
            start_url = os.getenv("OPENAI_BASE_URL", os.getenv("VLLM_URL", "http://localhost:8000/v1"))
            api_key = os.getenv("OPENAI_API_KEY", "EMPTY")
            model_name = os.getenv("MODEL_NAME", os.getenv("MODEL_ID", "model-name"))

            model = OpenAIModel(
                model_id=model_name,
                client_args={
                    "base_url": start_url,
                    "api_key": api_key,
                }
            )

            self._agent = Agent(
                name="summarizer",
                system_prompt=SUMMARIZE_PROMPT.format(target_size=self.target_size),
                model=model,
            )

        return self._agent

    def should_summarize(self, text: str) -> bool:
        """Check if text exceeds the summarization threshold."""
        return len(text) > self.threshold

    def _truncate(self, text: str) -> str:
        """Simple truncation fallback (no LLM call)."""
        truncated = text[:self.target_size]
        # Try to break at a line boundary
        last_newline = truncated.rfind('\n')
        if last_newline > self.target_size * 0.5:
            truncated = truncated[:last_newline]
        return f"[Truncated: {len(text):,} → {len(truncated):,} chars]\n\n{truncated}..."

    def summarize(self, text: str, context: str = "") -> str:
        """Summarize text if it exceeds threshold.

        Args:
            text: The text to potentially summarize.
            context: Optional context about what the text is (e.g., task description).

        Returns:
            Original text if under threshold, otherwise summarized version.
        """
        if not self.should_summarize(text):
            return text

        # Child agents: skip LLM summarization to avoid recursive overflow
        # on the same small-context model. Just truncate.
        depth = int(os.environ.get("QQ_RECURSION_DEPTH", "0"))
        if depth > 0:
            logger.info(f"Child agent (depth={depth}): truncating instead of LLM summarization")
            return self._truncate(text)

        try:
            agent = self._get_agent()

            prompt = f"Summarize this output"
            if context:
                prompt += f" (from task: {context[:100]})"
            prompt += f":\n\n{text}"

            # Get summary from agent
            result = agent(prompt)

            # Extract text from result
            if hasattr(result, 'message') and hasattr(result.message, 'content'):
                summary = ""
                for block in result.message.content:
                    if hasattr(block, 'text'):
                        summary += block.text
            else:
                summary = str(result)

            # Add indicator that this was summarized
            original_len = len(text)
            summary_len = len(summary)
            header = f"[Summarized: {original_len:,} → {summary_len:,} chars]\n\n"

            return header + summary

        except Exception as e:
            logger.warning(f"Summarization failed: {e}, returning truncated output")
            # Fallback: return truncated output with marker
            truncated = text[:self.target_size]
            return f"[Summarization failed, truncated at {self.target_size} chars]\n\n{truncated}..."


# Global instance for convenience
_summarizer: Optional[OutputSummarizer] = None


def get_summarizer() -> OutputSummarizer:
    """Get or create the global summarizer instance."""
    global _summarizer
    if _summarizer is None:
        _summarizer = OutputSummarizer()
    return _summarizer


def summarize_if_needed(text: str, context: str = "") -> str:
    """Convenience function to summarize text if needed.

    Args:
        text: The text to potentially summarize.
        context: Optional context about what the text is.

    Returns:
        Original or summarized text.
    """
    return get_summarizer().summarize(text, context)
